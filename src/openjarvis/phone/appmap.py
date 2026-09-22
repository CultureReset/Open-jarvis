"""App Maps: how to work one app's screens, as data.

An App Map is execution knowledge, not reasoning. It says what the Messages
app on *this* phone looks like — which view is the compose field, which button
sends, how an incoming bubble is told apart from an outgoing one — as a list
of selectors with fallbacks. The procedure that drives the screen contains no
app-specific names at all; swap the map and it drives a different messaging
app.

Keeping it as data has a second purpose. A map is a claim about a specific
app version, and a wrong claim means a tap landing somewhere unintended. So a
map carries ``validated`` and the build it was confirmed against, and
:func:`load_app_map` refuses to hand back an unvalidated map unless the caller
says outright that it is calibrating. Selectors written from documentation are
a starting point for calibration on the real device, never a released
procedure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence

from openjarvis.phone.uitree import Selector, UiNode

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

DATA_DIR = Path(__file__).parent / "data"

# Everything the messaging procedure asks a map for. A map missing any of
# these cannot drive a send, so it is rejected at load rather than failing
# partway through composing a message.
REQUIRED_ELEMENTS = (
    "conversation_list_anchor",
    "start_new_conversation",
    "conversation_row",
    "recipient_field",
    "compose_field",
    "send_button",
    "message_bubble",
    "thread_anchor",
)

OPTIONAL_ELEMENTS = (
    "recipient_commit",
    "incoming_bubble",
    "outgoing_bubble",
    "send_failed",
    "bubble_timestamp",
    "search_field",
    "permission_allow",
)

SIDE_STRATEGIES = ("alignment", "selector")


class AppMapError(ValueError):
    """A map that cannot be trusted to drive a screen."""


class UnvalidatedAppMap(AppMapError):
    """A map that has not been confirmed against a real device."""


@dataclass
class AppMap:
    """One app's screens, by name."""

    id: str
    name: str
    version: str
    package: str
    launch_activity: str
    elements: Dict[str, List[Selector]] = field(default_factory=dict)
    validated: bool = False
    validated_on: str = ""
    app_versions: List[str] = field(default_factory=list)
    side_strategy: str = "alignment"
    outgoing_left_fraction: float = 0.4
    notes: str = ""
    source_path: str = ""

    def selectors(self, element: str) -> List[Selector]:
        """The alternatives for one named element, best first."""
        if element not in self.elements:
            if element in REQUIRED_ELEMENTS:
                raise AppMapError(
                    f"App Map {self.id!r} is missing required element {element!r}"
                )
            return []
        return self.elements[element]

    def has(self, element: str) -> bool:
        return bool(self.elements.get(element))

    def is_outgoing(self, bubble: UiNode, screen_width: int) -> bool:
        """Which side of the thread this bubble sits on.

        ``selector`` when the app labels the two kinds differently.
        ``alignment`` otherwise: a person reads a thread by which edge the
        bubble hugs, and so does this.
        """
        if self.side_strategy == "selector":
            for selector in self.selectors("outgoing_bubble"):
                if selector.matches(bubble):
                    return True
            for selector in self.selectors("incoming_bubble"):
                if selector.matches(bubble):
                    return False
            return False
        if screen_width <= 0:
            return False
        return bubble.bounds.left > screen_width * self.outgoing_left_fraction


def _selector_list(raw: object, element: str, map_id: str) -> List[Selector]:
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        raise AppMapError(
            f"App Map {map_id!r}: element {element!r} must be one selector table or a "
            f"non-empty list of them"
        )
    selectors = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise AppMapError(
                f"App Map {map_id!r}: element {element!r} contains {entry!r}, "
                f"not a table"
            )
        try:
            selector = Selector.from_dict(entry)
        except ValueError as exc:
            raise AppMapError(
                f"App Map {map_id!r}: element {element!r}: {exc}"
            ) from exc
        if selector.is_empty():
            raise AppMapError(
                f"App Map {map_id!r}: element {element!r} has an empty selector, which "
                f"would match the whole screen"
            )
        selectors.append(selector)
    return selectors


def parse_app_map(data: Dict[str, object], source_path: str = "") -> AppMap:
    section = data.get("app_map")
    if not isinstance(section, dict):
        raise AppMapError("An App Map file needs an [app_map] table")

    map_id = str(section.get("id") or Path(source_path).stem or "unnamed")
    package = str(section.get("package", ""))
    activity = str(section.get("launch_activity", ""))
    if not package or not activity:
        raise AppMapError(
            f"App Map {map_id!r} must name both 'package' and "
            f"'launch_activity'; without them the app cannot be opened"
        )

    raw_elements = section.get("elements")
    if not isinstance(raw_elements, dict):
        raise AppMapError(f"App Map {map_id!r} must have an [app_map.elements] table")
    unknown = set(raw_elements) - set(REQUIRED_ELEMENTS) - set(OPTIONAL_ELEMENTS)
    if unknown:
        raise AppMapError(
            f"App Map {map_id!r} declares unknown element(s): "
            f"{', '.join(sorted(unknown))}"
        )
    missing = [name for name in REQUIRED_ELEMENTS if name not in raw_elements]
    if missing:
        raise AppMapError(
            f"App Map {map_id!r} is missing required element(s): {', '.join(missing)}"
        )

    elements = {
        name: _selector_list(raw, name, map_id) for name, raw in raw_elements.items()
    }

    side_strategy = str(section.get("side_strategy", "alignment"))
    if side_strategy not in SIDE_STRATEGIES:
        raise AppMapError(
            f"App Map {map_id!r}: side_strategy must be one of "
            f"{', '.join(SIDE_STRATEGIES)}"
        )
    if side_strategy == "selector" and not (
        elements.get("incoming_bubble") or elements.get("outgoing_bubble")
    ):
        raise AppMapError(
            f"App Map {map_id!r}: side_strategy='selector' needs 'incoming_bubble' or "
            f"'outgoing_bubble' selectors"
        )

    fraction = section.get("outgoing_left_fraction", 0.4)
    if not isinstance(fraction, (int, float)) or not 0.0 < float(fraction) < 1.0:
        raise AppMapError(
            f"App Map {map_id!r}: outgoing_left_fraction must be between 0 and 1"
        )

    versions = section.get("app_versions", [])
    if not isinstance(versions, list):
        raise AppMapError(f"App Map {map_id!r}: app_versions must be a list")

    return AppMap(
        id=map_id,
        name=str(section.get("name", map_id)),
        version=str(section.get("version", "0.1.0")),
        package=package,
        launch_activity=activity,
        elements=elements,
        validated=bool(section.get("validated", False)),
        validated_on=str(section.get("validated_on", "")),
        app_versions=[str(item) for item in versions],
        side_strategy=side_strategy,
        outgoing_left_fraction=float(fraction),
        notes=str(section.get("notes", "")),
        source_path=source_path,
    )


def load_app_map(path: str | Path, *, calibrating: bool = False) -> AppMap:
    """Load an App Map from TOML.

    An unvalidated map loads only when the caller is calibrating it. Driving a
    live phone with selectors nobody has confirmed is how a message goes to
    the wrong conversation.
    """
    path = Path(path)
    if not path.exists():
        raise AppMapError(f"No App Map at {path}")
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    app_map = parse_app_map(data, source_path=str(path))
    if not app_map.validated and not calibrating:
        raise UnvalidatedAppMap(
            f"App Map {app_map.id!r} ({path}) is marked validated = false. Its "
            f"selectors have not been confirmed against a real device. Calibrate it "
            f"against the "
            f"phone with `jarvis phone calibrate`, set validated = true and record the "
            f"app build in validated_on, or load it with calibrating=True."
        )
    return app_map


def builtin_map_path(map_id: str) -> Path:
    return DATA_DIR / f"{map_id}.toml"


def list_app_maps() -> List[str]:
    """The App Maps shipped here.

    The data directory also holds files that are not App Maps, such as the
    display-name hints, so membership is decided by what is in the file --
    an [app_map] table -- rather than by where it sits.
    """
    if not DATA_DIR.exists():
        return []
    found = []
    for path in sorted(DATA_DIR.glob("*.toml")):
        try:
            with open(path, "rb") as handle:
                data = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if isinstance(data.get("app_map"), dict):
            found.append(path.stem)
    return found


def missing_on_screen(
    app_map: AppMap, screen: UiNode | None, elements: Sequence[str]
) -> List[str]:
    """Which of these named elements are not on the screen in front of us.

    This is the calibration report: run it on each screen of the real app and
    a map is either confirmed or told exactly what it got wrong.
    """
    from openjarvis.phone.uitree import find

    absent = []
    for name in elements:
        selectors = app_map.elements.get(name, [])
        if not selectors or find(screen, *selectors) is None:
            absent.append(name)
    return absent


__all__ = [
    "AppMap",
    "AppMapError",
    "UnvalidatedAppMap",
    "REQUIRED_ELEMENTS",
    "OPTIONAL_ELEMENTS",
    "parse_app_map",
    "load_app_map",
    "builtin_map_path",
    "list_app_maps",
    "missing_on_screen",
    "DATA_DIR",
]
