"""The phone that is part of the machine, driven by its screen.

The Android plugged into the box is a component, not a user's handset. It has
its own SIM and its own number, and the agent uses it the way a hand does: it
opens an app, taps, types, and reads what is on the screen.

* :mod:`openjarvis.phone.device` — the hand and the eyes, restricted in code
  to screen verbs.
* :mod:`openjarvis.phone.uitree` — the screen, parsed.
* :mod:`openjarvis.phone.appmap` — per-app screen knowledge, as data, and the
  validation gate that keeps an unconfirmed map off a live phone.
* :mod:`openjarvis.phone.messages` — the texting procedure and its evidence
  rules.
"""

from openjarvis.phone.appmap import (
    AppMap,
    AppMapError,
    UnvalidatedAppMap,
    builtin_map_path,
    list_app_maps,
    load_app_map,
)
from openjarvis.phone.device import (
    ForbiddenDeviceCommand,
    PhoneDevice,
    ScreenOnlyShell,
    is_screen_verb,
)
from openjarvis.phone.messages import (
    NOT_SENT,
    SENT,
    UNCERTAIN,
    InboxWatcher,
    MessagesProcedure,
    ScreenMessage,
    SendOutcome,
)
from openjarvis.phone.uitree import Selector, UiNode, parse_ui_dump

__all__ = [
    "AppMap",
    "AppMapError",
    "UnvalidatedAppMap",
    "load_app_map",
    "builtin_map_path",
    "list_app_maps",
    "PhoneDevice",
    "ScreenOnlyShell",
    "ForbiddenDeviceCommand",
    "is_screen_verb",
    "MessagesProcedure",
    "InboxWatcher",
    "SendOutcome",
    "ScreenMessage",
    "SENT",
    "NOT_SENT",
    "UNCERTAIN",
    "Selector",
    "UiNode",
    "parse_ui_dump",
]
