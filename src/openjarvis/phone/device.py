"""The phone as a component of the machine: taps, typing, and looking.

The Android that plugs into the box is part of the box. What the agent is
allowed to do with it is exactly what a hand can do — wake it, tap a point,
swipe, press a key, type into whatever field has focus, and look at the
screen. Nothing else.

That is not a convention here, it is enforced. :class:`ScreenOnlyShell`
matches every command against an allowlist of screen verbs and raises on
anything else, so the shortcuts that would defeat the point cannot be issued
even by mistake:

* ``service call isms ...`` — sends an SMS with no UI involved at all.
* ``content query --uri content://sms/...`` — reads the message database
  instead of reading the screen.
* ``am start ... -d sms:...`` / ``--es sms_body ...`` — pre-fills a message
  through an intent rather than typing it.
* ``pm grant``, ``su``, ``settings put`` — widening what the device allows.

Opening an app is the one thing done by name rather than by hunting an icon
on a launcher page: ``am start`` on the app's own MAIN activity, which is
what the launcher itself does when an icon is tapped. Everything after that
— which conversation, which field, which words, which button — is found on
screen and reached by coordinate.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence

from openjarvis.phone.uitree import Selector, UiNode, find, find_all, parse_ui_dump

logger = logging.getLogger(__name__)

DUMP_PATH = "/sdcard/ng-screen.xml"
TYPE_CHUNK = 180


class ForbiddenDeviceCommand(RuntimeError):
    """Raised for a command that is not a screen verb.

    The message names the command so the refusal is auditable rather than a
    silent no-op.
    """


class DeviceUnreachable(RuntimeError):
    """The bound phone did not answer."""


# Every command the agent may put on the wire. Anchored, and narrow on
# purpose: a pattern that admits arbitrary arguments admits the backdoor.
PERMITTED_COMMANDS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^input tap \d{1,5} \d{1,5}$"),
    re.compile(r"^input swipe \d{1,5} \d{1,5} \d{1,5} \d{1,5}(?: \d{1,5})?$"),
    re.compile(r"^input keyevent KEYCODE_[A-Z0-9_]{1,32}$"),
    re.compile(r"^input text '[^']*'$"),
    re.compile(r"^uiautomator dump " + re.escape(DUMP_PATH) + r"$"),
    re.compile(r"^cat " + re.escape(DUMP_PATH) + r"$"),
    re.compile(r"^rm -f " + re.escape(DUMP_PATH) + r"$"),
    re.compile(
        r"^am start -W -a android\.intent\.action\.MAIN"
        r" -c android\.intent\.category\.LAUNCHER"
        r" -n [A-Za-z0-9_.]{1,128}/[A-Za-z0-9_.$]{1,128}$"
    ),
    re.compile(r"^am force-stop [A-Za-z0-9_.]{1,128}$"),
    re.compile(
        r"^getprop (?:gsm\.sim\.state|ro\.build\.version\.release|ro\.product\.model)$"
    ),
    re.compile(r"^dumpsys package [A-Za-z0-9_.]{1,128}$"),
    re.compile(r"^wm size$"),
    re.compile(r"^echo ok$"),
)


def is_screen_verb(command: str) -> bool:
    """Would this command be allowed through?"""
    return any(pattern.fullmatch(command) for pattern in PERMITTED_COMMANDS)


def encode_typing(body: str) -> List[str]:
    """Turn text into the commands that type it.

    ``input text`` reads ``%s`` as a space and has no escape for a single
    quote, so spaces are encoded and quotes are pressed as a key. Chunking
    keeps each command well inside the device shell's argument limits.

    There is no escape for a literal ``%s`` either, which is why nothing here
    assumes the characters arrived: the caller reads the field back off the
    screen and compares before anything is sent.
    """
    commands: List[str] = []
    for segment in body.split("'"):
        if segment:
            encoded = segment.replace(" ", "%s")
            for start in range(0, len(encoded), TYPE_CHUNK):
                commands.append(f"input text '{encoded[start : start + TYPE_CHUNK]}'")
        commands.append("input keyevent KEYCODE_APOSTROPHE")
    return (
        commands[:-1] if commands and commands[-1].endswith("APOSTROPHE") else commands
    )


@dataclass
class ShellResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class ScreenOnlyShell:
    """adb, bound to one serial, restricted to screen verbs."""

    def __init__(self, serial: str, adb: str = "adb") -> None:
        if not serial:
            raise ValueError("A phone driver must be bound to one device serial")
        self.serial = serial
        self.adb = adb

    def available(self) -> bool:
        return shutil.which(self.adb) is not None

    def devices(self) -> List[str]:
        result = self._raw([self.adb, "devices"])
        if not result.ok:
            return []
        attached = []
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                attached.append(parts[0])
        return attached

    def shell(self, command: str, timeout: int = 20) -> ShellResult:
        if not is_screen_verb(command):
            raise ForbiddenDeviceCommand(
                f"Refused: {command!r} is not a screen verb. This driver taps, types, "
                f"presses keys and reads the screen. Message content and history "
                f"come from the screen, never from the SMS database or a send API."
            )
        return self._raw(
            [self.adb, "-s", self.serial, "shell", command], timeout=timeout
        )

    @staticmethod
    def _raw(argv: Sequence[str], timeout: int = 20) -> ShellResult:
        try:
            completed = subprocess.run(
                list(argv), capture_output=True, text=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired:
            return ShellResult(124, "", f"timed out after {timeout}s")
        except FileNotFoundError as exc:
            return ShellResult(127, "", str(exc))
        return ShellResult(completed.returncode, completed.stdout, completed.stderr)


class PhoneDevice:
    """A hand on the bound phone, plus eyes on its screen.

    Held under a lock. Two things driving the same screen at once produce taps
    landing on whatever moved underneath them, which on a messaging app means
    a message to the wrong person.
    """

    def __init__(
        self, serial: str, shell: Optional[ScreenOnlyShell] = None, settle: float = 0.6
    ) -> None:
        self.serial = serial
        self.shell = shell or ScreenOnlyShell(serial)
        self.settle = settle
        self.lock = threading.RLock()

    # --- state ----------------------------------------------------------

    def attached(self) -> bool:
        return self.serial in self.shell.devices()

    def reachable(self) -> bool:
        return self.shell.shell("echo ok").stdout.strip() == "ok"

    def sim_ready(self) -> bool:
        result = self.shell.shell("getprop gsm.sim.state")
        return result.ok and "READY" in result.stdout.upper()

    def model(self) -> str:
        return self.shell.shell("getprop ro.product.model").stdout.strip()

    def screen_size(self) -> Optional[tuple[int, int]]:
        result = self.shell.shell("wm size")
        match = re.search(r"(\d+)x(\d+)", result.stdout)
        return (int(match.group(1)), int(match.group(2))) if match else None

    def package_version(self, package: str) -> str:
        result = self.shell.shell(f"dumpsys package {package}", timeout=30)
        match = re.search(r"versionName=(\S+)", result.stdout)
        return match.group(1) if match else ""

    # --- hand -----------------------------------------------------------

    def wake(self) -> None:
        self.press("KEYCODE_WAKEUP")

    def home(self) -> None:
        self.press("KEYCODE_HOME")

    def back(self) -> None:
        self.press("KEYCODE_BACK")

    def press(self, keycode: str) -> bool:
        return self.shell.shell(f"input keyevent {keycode}").ok

    def tap(self, x: int, y: int) -> bool:
        if x < 0 or y < 0:
            logger.error("Refusing a tap at (%s, %s): off screen", x, y)
            return False
        ok = self.shell.shell(f"input tap {int(x)} {int(y)}").ok
        time.sleep(self.settle)
        return ok

    def tap_node(self, node: UiNode) -> bool:
        """Tap the thing that was found, at the point a person would touch."""
        target = node.nearest_clickable()
        if target.bounds.is_empty():
            logger.error("Refusing to tap %r: it has no area on screen", node.label)
            return False
        x, y = target.center
        return self.tap(x, y)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 300) -> bool:
        ok = self.shell.shell(
            f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(ms)}"
        ).ok
        time.sleep(self.settle)
        return ok

    def type_text(self, body: str) -> bool:
        """Type into whatever has focus. Arrival is verified by the caller."""
        if not body:
            return True
        if any(ord(char) > 126 for char in body) or "%s" in body:
            logger.warning(
                "This text has characters the device keyboard bridge cannot "
                "represent exactly; the field will be read back and the send "
                "abandoned if the device did not take them."
            )
        for command in encode_typing(body):
            if not self.shell.shell(command).ok:
                return False
        time.sleep(self.settle)
        return True

    def clear_focused_field(self, length: int, headroom: int = 4) -> None:
        """Empty the focused field with the delete key, as a person would.

        ``length`` is what was read off the screen, so the number of presses
        is bounded by what is actually there rather than by a guess.
        """
        self.press("KEYCODE_MOVE_END")
        for _ in range(max(0, length) + max(0, headroom)):
            self.shell.shell("input keyevent KEYCODE_DEL")
        time.sleep(self.settle)

    # --- eyes -----------------------------------------------------------

    def open_app(self, package: str, activity: str) -> bool:
        """Open the app the way tapping its launcher icon does."""
        self.wake()
        self.home()
        result = self.shell.shell(
            "am start -W -a android.intent.action.MAIN"
            " -c android.intent.category.LAUNCHER"
            f" -n {package}/{activity}",
            timeout=30,
        )
        time.sleep(self.settle * 2)
        return result.ok and "Error" not in result.stdout

    def screen(self, retries: int = 2) -> Optional[UiNode]:
        """Read the screen. None if it could not be read."""
        for attempt in range(retries + 1):
            dumped = self.shell.shell(f"uiautomator dump {DUMP_PATH}", timeout=30)
            if dumped.ok:
                read = self.shell.shell(f"cat {DUMP_PATH}", timeout=30)
                tree = parse_ui_dump(read.stdout)
                self.shell.shell(f"rm -f {DUMP_PATH}")
                if tree is not None:
                    return tree
            if attempt < retries:
                time.sleep(self.settle)
        logger.warning("Could not read the screen of %s", self.serial)
        return None

    def look_for(self, *selectors: Selector, timeout: float = 6.0) -> Optional[UiNode]:
        """Wait for something to appear on screen, then return it."""
        deadline = time.monotonic() + timeout
        while True:
            node = find(self.screen(), *selectors)
            if node is not None:
                return node
            if time.monotonic() >= deadline:
                return None
            time.sleep(max(self.settle, 0.05))

    def look_for_all(self, *selectors: Selector) -> List[UiNode]:
        return find_all(self.screen(), *selectors)

    def scroll_up(self) -> bool:
        """Scroll back through a list, to see older items."""
        size = self.screen_size()
        if not size:
            return False
        width, height = size
        return self.swipe(width // 2, height // 3, width // 2, int(height * 0.8), 400)


__all__ = [
    "PhoneDevice",
    "ScreenOnlyShell",
    "ShellResult",
    "ForbiddenDeviceCommand",
    "DeviceUnreachable",
    "PERMITTED_COMMANDS",
    "is_screen_verb",
    "encode_typing",
    "DUMP_PATH",
]
