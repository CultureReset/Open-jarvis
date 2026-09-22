"""What is installed on the box's phone.

The owner's apps have to appear on the shell. They already have accounts in
them, so the shell showing Facebook, Toast, Square or a music app is not a
new integration — it is the box admitting what it can already reach.

This asks the device for its own app list, the same question a launcher asks
to draw its icons: which third-party packages are installed, and which
activity a tap on the icon would start. Both are read-only. Nothing here
reads message content, and the write forms of ``pm`` are not reachable
through the driver at all.

Display names are the one thing the device does not hand over cheaply.
``pm`` returns ``com.facebook.katana``, not "Facebook". So a name is derived
from the package and may be refined by ``data/app_labels.toml`` — display
hints, nothing more, and every app says which of the two its name came from
so the shell never presents a guess as the app's real name.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from openjarvis.phone.device import PhoneDevice

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

LABELS_PATH = Path(__file__).parent / "data" / "app_labels.toml"
PACKAGE_LINE = re.compile(r"^package:([A-Za-z0-9_.]+)$")
COMPONENT = re.compile(r"^([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)$")

DERIVED = "package"
HINTED = "labels_file"


@dataclass(frozen=True)
class InstalledApp:
    """One app on the phone, and how sure we are of its name."""

    package: str
    activity: str
    label: str
    label_source: str

    @property
    def launchable(self) -> bool:
        return bool(self.activity)

    @property
    def name_is_derived(self) -> bool:
        """True when the name was guessed from the package, not looked up."""
        return self.label_source == DERIVED


def parse_packages(output: str) -> List[str]:
    """Package names out of ``pm list packages -3``."""
    found = []
    for line in output.splitlines():
        match = PACKAGE_LINE.match(line.strip())
        if match:
            found.append(match.group(1))
    return sorted(set(found))


def parse_component(output: str) -> str:
    """The ``package/activity`` line out of ``resolve-activity --brief``.

    The command prints a priority line first on some builds, so every line is
    considered and anything that is not a component is ignored.
    """
    for line in output.splitlines():
        line = line.strip()
        if COMPONENT.match(line):
            return line
    return ""


def derive_label(package: str) -> str:
    """A readable name from a package, when nothing better is available.

    ``com.google.android.apps.messaging`` becomes "Messaging". It is a guess,
    and it is marked as one.
    """
    parts = [part for part in package.split(".") if part]
    if not parts:
        return package
    tail = parts[-1]
    # A trailing "android" or "app" segment is never the app's name.
    if tail in ("android", "app", "apps", "mobile", "client") and len(parts) > 1:
        tail = parts[-2]
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", tail).replace("_", " ")
    return words.strip().title()


def load_label_hints(path: Path | str = LABELS_PATH) -> Dict[str, str]:
    """Display-name hints. Missing or malformed means no hints, not an error."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logger.warning("Could not read app label hints at %s: %s", path, exc)
        return {}
    labels = data.get("labels")
    if not isinstance(labels, dict):
        return {}
    return {
        str(package): str(label)
        for package, label in labels.items()
        if isinstance(label, str) and label.strip()
    }


def list_installed(
    device: PhoneDevice,
    *,
    hints: Optional[Dict[str, str]] = None,
    limit: int = 120,
) -> List[InstalledApp]:
    """The phone's own app list, launch activities resolved.

    Held under the device lock, because resolving a hundred activities while
    a message is being typed would interleave with the typing.
    """
    hints = load_label_hints() if hints is None else hints
    with device.lock:
        if not device.attached():
            logger.info("No phone attached to %s; no apps to list", device.serial)
            return []
        listing = device.shell.shell("pm list packages -3", timeout=30)
        if not listing.ok:
            logger.warning("Could not list packages on %s", device.serial)
            return []

        apps: List[InstalledApp] = []
        for package in parse_packages(listing.stdout)[:limit]:
            resolved = device.shell.shell(
                "cmd package resolve-activity --brief"
                f" -c android.intent.category.LAUNCHER {package}",
                timeout=20,
            )
            component = parse_component(resolved.stdout) if resolved.ok else ""
            activity = component.split("/", 1)[1] if "/" in component else ""
            hinted = hints.get(package)
            apps.append(
                InstalledApp(
                    package=package,
                    activity=activity,
                    label=hinted or derive_label(package),
                    label_source=HINTED if hinted else DERIVED,
                )
            )
    return apps


def launchable(apps: List[InstalledApp]) -> List[InstalledApp]:
    """Only the apps a tap could actually open, in name order."""
    return sorted(
        (app for app in apps if app.launchable),
        key=lambda app: app.label.casefold(),
    )


__all__ = [
    "InstalledApp",
    "list_installed",
    "launchable",
    "parse_packages",
    "parse_component",
    "derive_label",
    "load_label_hints",
    "DERIVED",
    "HINTED",
    "LABELS_PATH",
]
