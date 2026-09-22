"""``jarvis phone`` — the phone that is part of the box, and its App Maps.

Three jobs, all of them about the screen:

``jarvis phone screen``
    Print what is on the phone's screen right now, with the identifiers a
    selector would use. This is how a map gets written.

``jarvis phone maps``
    List the App Maps and say which have been confirmed against a device.

``jarvis phone calibrate``
    Walk the app's screens and report, per screen, which of the map's named
    elements were not found. That report is the work: fix the selectors it
    names, then set ``validated = true`` and record the app build in
    ``validated_on``. Nothing here marks a map validated on its own — that is
    a claim about hardware, and only a person who watched it happen can make
    it.
"""

from __future__ import annotations

import os
from typing import List, Optional, Sequence

import click
from rich.console import Console
from rich.table import Table

console = Console()

CALIBRATION_SCREENS = (
    (
        "conversation list",
        ("conversation_list_anchor", "start_new_conversation", "conversation_row"),
    ),
    ("new conversation", ("recipient_field", "compose_field")),
    (
        "an open thread",
        ("thread_anchor", "compose_field", "send_button", "message_bubble"),
    ),
)


def _serial(given: Optional[str]) -> str:
    serial = given or os.environ.get("NG_ANDROID_SERIAL", "")
    if not serial:
        raise click.ClickException(
            "No device serial. Pass --serial or set NG_ANDROID_SERIAL. The phone this "
            "box drives is named explicitly so a swapped cable cannot silently change "
            "which SIM speaks for the owner."
        )
    return serial


def _device(serial: str):
    from openjarvis.phone.device import PhoneDevice, ScreenOnlyShell

    shell = ScreenOnlyShell(serial)
    if not shell.available():
        raise click.ClickException("adb was not found on PATH.")
    attached = shell.devices()
    if serial not in attached:
        raise click.ClickException(
            f"{serial} is not attached (attached: {', '.join(attached) or 'none'})."
        )
    return PhoneDevice(serial, shell)


def _load(map_ref: str):
    from openjarvis.channels.android_sim import resolve_app_map

    try:
        return resolve_app_map(map_ref, calibrating=True)
    except Exception as exc:  # AppMapError and friends
        raise click.ClickException(str(exc)) from exc


@click.group()
def phone() -> None:
    """The phone plugged into the box, driven by its screen."""


@phone.command("maps")
def maps_cmd() -> None:
    """List App Maps and whether they have been confirmed on a device."""
    from openjarvis.phone.appmap import builtin_map_path, list_app_maps, load_app_map

    names = list_app_maps()
    if not names:
        console.print("[yellow]No App Maps are installed.[/yellow]")
        return

    table = Table(title="App Maps")
    table.add_column("id")
    table.add_column("app")
    table.add_column("package")
    table.add_column("validated")
    table.add_column("confirmed against")
    for name in names:
        app_map = load_app_map(builtin_map_path(name), calibrating=True)
        table.add_row(
            app_map.id,
            app_map.name,
            app_map.package,
            "[green]yes[/green]" if app_map.validated else "[red]no[/red]",
            app_map.validated_on or "—",
        )
    console.print(table)
    console.print(
        "\nAn unvalidated map will not drive a live phone. Run "
        "[bold]jarvis phone calibrate[/bold] against the device, fix what it reports, "
        "then set validated = true and record the app build in validated_on."
    )


@phone.command("screen")
@click.option("--serial", default=None, help="adb serial of the box's phone.")
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Include nodes with no text and no description.",
)
def screen_cmd(serial: Optional[str], show_all: bool) -> None:
    """Print what is on the phone's screen, with selector identifiers."""
    device = _device(_serial(serial))
    tree = device.screen()
    if tree is None:
        raise click.ClickException("Could not read the screen.")

    table = Table(title=f"{device.serial} — what is on screen")
    table.add_column("label")
    table.add_column("resource_id")
    table.add_column("content_desc")
    table.add_column("class")
    table.add_column("bounds")
    table.add_column("tap")
    shown = 0
    for node in tree.walk():
        if node.bounds.is_empty():
            continue
        if not show_all and not node.label:
            continue
        rid = node.resource_id.split(":id/")[-1] if node.resource_id else ""
        table.add_row(
            node.label[:40],
            rid,
            node.content_desc[:30],
            node.cls.split(".")[-1],
            f"[{node.bounds.left},{node.bounds.top}]"
            f"[{node.bounds.right},{node.bounds.bottom}]",
            "yes" if node.clickable else "",
        )
        shown += 1
    console.print(table)
    console.print(f"{shown} node(s) with something readable on them.")


@phone.command("calibrate")
@click.option(
    "--map",
    "map_ref",
    default="google_messages",
    help="App Map id or path to a TOML file.",
)
@click.option("--serial", default=None, help="adb serial of the box's phone.")
@click.option(
    "--screen",
    "only",
    default=None,
    help="Calibrate one screen only: list, new, or thread.",
)
def calibrate_cmd(map_ref: str, serial: Optional[str], only: Optional[str]) -> None:
    """Report which of a map's elements are not on the app's screens."""
    from openjarvis.phone.appmap import missing_on_screen

    app_map = _load(map_ref)
    device = _device(_serial(serial))

    console.print(
        f"Calibrating App Map [bold]{app_map.id}[/bold] against "
        f"[bold]{device.serial}[/bold] ({device.model() or 'unknown model'})."
    )
    installed = device.package_version(app_map.package)
    console.print(f"{app_map.package} on this phone: {installed or 'not reported'}\n")

    wanted = _selected_screens(only)
    failures: List[str] = []
    for index, (title, elements) in enumerate(wanted):
        if index == 0:
            console.print("Opening the app…")
            if not device.open_app(app_map.package, app_map.launch_activity):
                raise click.ClickException(f"Could not open {app_map.package}.")
        else:
            click.confirm(
                f"Put the phone on [{title}] and press Enter",
                default=True,
                show_default=False,
                abort=False,
            )
        absent = missing_on_screen(app_map, device.screen(), elements)
        found = [name for name in elements if name not in absent]
        console.print(f"[bold]{title}[/bold]")
        for name in found:
            console.print(f"  [green]found[/green]   {name}")
        for name in absent:
            console.print(f"  [red]missing[/red] {name}")
            failures.append(f"{title}: {name}")
        console.print()

    if failures:
        console.print(
            f"[red]{len(failures)} element(s) were not found.[/red] Fix their "
            f"selectors in {app_map.source_path or app_map.id} against "
            f"[bold]jarvis phone screen[/bold], then run this again."
        )
        raise SystemExit(1)

    console.print("[green]Every element this map names was found on screen.[/green]")
    if app_map.validated:
        console.print("The map is already marked validated.")
        return
    console.print(
        "\nThe map is still marked [bold]validated = false[/bold]. Set it to true and "
        f"put the app build in validated_on, for example:\n\n"
        f'  validated = true\n  validated_on = "{app_map.package} {installed} on '
        f'{device.model()}"\n\n'
        "It is left to you on purpose: marking a map validated is a claim that it was "
        "seen working on this hardware."
    )


def _selected_screens(only: Optional[str]) -> Sequence:
    if not only:
        return CALIBRATION_SCREENS
    keys = {"list": 0, "new": 1, "thread": 2}
    if only not in keys:
        raise click.ClickException(f"--screen must be one of: {', '.join(keys)}")
    return [CALIBRATION_SCREENS[keys[only]]]


__all__ = ["phone"]
