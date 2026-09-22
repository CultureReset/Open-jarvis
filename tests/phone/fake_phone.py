"""A MOCK phone for tests. Not hardware.

This renders a small messaging app as ``uiautomator dump`` XML and applies
taps and keystrokes to it, so the screen-driving procedure can be exercised
without a device. It proves the procedure's logic and its evidence rules.

It proves nothing about a real phone. Every command still passes through
``is_screen_verb``, so the tests do check that the driver only ever issues
screen verbs, but selector correctness, timing, and whether a carrier
accepted anything are only answerable on the physical device. No test in this
file may be cited for a hardware acceptance gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from openjarvis.phone.device import ShellResult, is_screen_verb

PACKAGE = "com.google.android.apps.messaging"
WIDTH, HEIGHT = 1080, 2340
FRAME = "android.widget.FrameLayout"

LIST = "list"
NEW = "new"
THREAD = "thread"


def node(
    cls: str,
    *,
    rid: str = "",
    text: str = "",
    desc: str = "",
    bounds: Tuple[int, int, int, int] = (0, 0, 0, 0),
    clickable: bool = False,
    children: str = "",
) -> str:
    left, top, right, bottom = bounds
    rid_full = f"{PACKAGE}:id/{rid}" if rid else ""
    attrs = (
        f'index="0" text="{_x(text)}" resource-id="{rid_full}" class="{cls}" '
        f'package="{PACKAGE}" content-desc="{_x(desc)}" checkable="false" '
        f'checked="false" clickable="{str(clickable).lower()}" enabled="true" '
        f'focusable="true" focused="false" scrollable="false" long-clickable="false" '
        f'password="false" selected="false" bounds="[{left},{top}][{right},{bottom}]"'
    )
    if children:
        return f"<node {attrs}>{children}</node>"
    return f"<node {attrs}/>"


def _x(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


@dataclass
class Bubble:
    body: str
    outgoing: bool
    stamp: str = "now"


@dataclass
class Thread:
    name: str
    bubbles: List[Bubble] = field(default_factory=list)
    # What the row's time label reads. A real messaging app relabels this on
    # every new message ("now", "2m", "2:14 PM"), which is the cue that
    # something changed in a conversation without opening it.
    row_time: str = "now"

    @property
    def preview(self) -> str:
        return self.bubbles[-1].body if self.bubbles else ""


@dataclass
class FakePhone:
    """A stand-in for :class:`ScreenOnlyShell` plus the app behind it."""

    serial: str = "MOCKSERIAL1"
    attached: bool = True
    sim: str = "READY"
    adb_present: bool = True
    screen_name: str = LIST
    threads: Dict[str, Thread] = field(default_factory=dict)
    open_thread: str = ""
    recipient: str = ""
    compose: str = ""
    focus: str = ""
    commands: List[str] = field(default_factory=list)
    refused: List[str] = field(default_factory=list)
    send_fails: bool = False
    swallow_typing: bool = False
    drop_after: int = 0
    clock: int = 0
    # package -> launcher activity. An empty activity means installed but not
    # launchable, which real devices have plenty of.
    installed: Dict[str, str] = field(default_factory=dict)

    # --- ScreenOnlyShell surface ---------------------------------------

    def available(self) -> bool:
        return self.adb_present

    def devices(self) -> List[str]:
        return [self.serial] if self.attached else []

    def shell(self, command: str, timeout: int = 20) -> ShellResult:
        if not is_screen_verb(command):
            self.refused.append(command)
            from openjarvis.phone.device import ForbiddenDeviceCommand

            raise ForbiddenDeviceCommand(command)
        self.commands.append(command)
        return self._apply(command)

    # --- behaviour ------------------------------------------------------

    def _apply(self, command: str) -> ShellResult:
        if command == "echo ok":
            return ShellResult(0, "ok\n", "")
        if command == "getprop gsm.sim.state":
            return ShellResult(0, f"{self.sim}\n", "")
        if command == "getprop ro.product.model":
            return ShellResult(0, "Mock Phone\n", "")
        if command == "wm size":
            return ShellResult(0, f"Physical size: {WIDTH}x{HEIGHT}\n", "")
        if command.startswith("dumpsys package"):
            return ShellResult(0, "    versionName=mock.0\n", "")
        if command == "pm list packages -3":
            body = "".join(f"package:{name}\n" for name in sorted(self.installed))
            return ShellResult(0, body, "")
        if command.startswith("cmd package resolve-activity"):
            package = command.split()[-1]
            activity = self.installed.get(package, "")
            if not activity:
                return ShellResult(0, "No activity found\n", "")
            return ShellResult(
                0, f"priority=0 preferredOrder=0\n{package}/{activity}\n", ""
            )
        if command.startswith("am force-stop"):
            return ShellResult(0, "", "")
        if command.startswith("am start"):
            if f"-n {PACKAGE}/" not in command:
                return ShellResult(0, "Error: Activity not started\n", "")
            self.screen_name = LIST
            self.open_thread = ""
            self.recipient = ""
            self.focus = ""
            return ShellResult(0, "Status: ok\n", "")
        if command.startswith("uiautomator dump"):
            return ShellResult(0, "UI hierchary dumped to: /sdcard/ng-screen.xml\n", "")
        if command.startswith("cat "):
            return ShellResult(0, self.render(), "")
        if command.startswith("rm -f "):
            return ShellResult(0, "", "")
        if command.startswith("input tap "):
            _, _, x, y = command.split()
            return self._tap(int(x), int(y))
        if command.startswith("input swipe "):
            return ShellResult(0, "", "")
        if command.startswith("input keyevent "):
            return self._key(command.split()[-1])
        if command.startswith("input text "):
            return self._type(command[len("input text ") :].strip("'"))
        return ShellResult(1, "", f"unhandled by the mock: {command}")

    def _tap(self, x: int, y: int) -> ShellResult:
        for name, bounds, kind in self._targets():
            left, top, right, bottom = bounds
            if left <= x <= right and top <= y <= bottom:
                self._activate(name, kind)
                return ShellResult(0, "", "")
        return ShellResult(0, "", "")

    def _activate(self, name: str, kind: str) -> None:
        if kind == "field":
            self.focus = name
        elif name == "start_new":
            self.screen_name = NEW
            self.recipient = ""
            self.compose = ""
            self.focus = ""
        elif name == "send":
            self._send()
        elif name.startswith("row:"):
            self.open_thread = name[4:]
            self.screen_name = THREAD
            self.focus = ""

    def _send(self) -> None:
        if not self.compose:
            return
        target = self.open_thread or self.recipient
        if not target:
            return
        thread = self.threads.setdefault(target, Thread(name=target))
        thread.bubbles.append(
            Bubble(
                body=self.compose,
                outgoing=True,
                stamp="Not sent" if self.send_fails else "now",
            )
        )
        self.clock += 1
        thread.row_time = f"{self.clock}m"
        self.compose = ""
        self.open_thread = target
        self.screen_name = THREAD

    def _key(self, keycode: str) -> ShellResult:
        if keycode == "KEYCODE_DEL":
            if self.focus == "compose" and self.compose:
                self.compose = self.compose[:-1]
            elif self.focus == "recipient" and self.recipient:
                self.recipient = self.recipient[:-1]
        elif keycode == "KEYCODE_APOSTROPHE":
            self._type_raw("'")
        elif keycode == "KEYCODE_ENTER" and self.screen_name == NEW:
            self.open_thread = self.recipient
            self.threads.setdefault(self.recipient, Thread(name=self.recipient))
            self.screen_name = THREAD
            self.focus = ""
        elif keycode in ("KEYCODE_HOME", "KEYCODE_WAKEUP"):
            pass
        elif keycode == "KEYCODE_BACK":
            if self.screen_name in (THREAD, NEW):
                self.screen_name = LIST
                self.open_thread = ""
                self.focus = ""
        return ShellResult(0, "", "")

    def _type(self, encoded: str) -> ShellResult:
        self._type_raw(encoded.replace("%s", " "))
        return ShellResult(0, "", "")

    def _type_raw(self, text: str) -> None:
        if self.swallow_typing:
            return
        if self.drop_after:
            room = max(0, self.drop_after - len(self.compose))
            text = text[:room] if self.focus == "compose" else text
        if self.focus == "compose":
            self.compose += text
        elif self.focus == "recipient":
            self.recipient += text

    # --- rendering ------------------------------------------------------

    def _targets(self) -> List[Tuple[str, Tuple[int, int, int, int], str]]:
        if self.screen_name == LIST:
            targets = [("start_new", (900, 2100, 1040, 2240), "button")]
            for index, name in enumerate(sorted(self.threads)):
                top = 300 + index * 200
                targets.append((f"row:{name}", (0, top, WIDTH, top + 180), "row"))
            return targets
        if self.screen_name == NEW:
            return [
                ("recipient", (40, 200, 1040, 280), "field"),
                ("compose", (40, 2100, 880, 2200), "field"),
            ]
        return [
            ("compose", (40, 2100, 880, 2200), "field"),
            ("send", (920, 2100, 1040, 2200), "button"),
        ]

    def render(self) -> str:
        if self.screen_name == LIST:
            rows = ""
            for index, name in enumerate(sorted(self.threads)):
                top = 300 + index * 200
                rows += node(
                    "android.widget.LinearLayout",
                    bounds=(0, top, WIDTH, top + 180),
                    clickable=True,
                    children=(
                        node(
                            "android.widget.TextView",
                            rid="conversation_name",
                            text=name,
                            bounds=(40, top + 10, 700, top + 70),
                        )
                        + node(
                            "android.widget.TextView",
                            rid="snippet_text",
                            text=self.threads[name].preview,
                            bounds=(40, top + 80, 900, top + 140),
                        )
                        + node(
                            "android.widget.TextView",
                            rid="conversation_timestamp",
                            text=self.threads[name].row_time,
                            bounds=(900, top + 10, 1040, top + 70),
                        )
                    ),
                )
            body = node(
                "android.widget.FrameLayout",
                rid="conversation_list",
                bounds=(0, 200, WIDTH, 2080),
                children=rows,
            ) + node(
                "android.widget.ImageButton",
                rid="start_new_conversation_button",
                desc="Start chat",
                bounds=(900, 2100, 1040, 2240),
                clickable=True,
            )
        elif self.screen_name == NEW:
            body = node(
                "android.widget.EditText",
                rid="recipient_text_view",
                text=self.recipient,
                bounds=(40, 200, 1040, 280),
                clickable=True,
            ) + node(
                "android.widget.EditText",
                rid="compose_message_text",
                text=self.compose,
                desc="Text message",
                bounds=(40, 2100, 880, 2200),
                clickable=True,
            )
        else:
            thread = self.threads.get(self.open_thread, Thread(name=self.open_thread))
            bubbles = ""
            for index, bubble in enumerate(thread.bubbles):
                top = 300 + index * 160
                left, right = (560, 1040) if bubble.outgoing else (40, 520)
                bubbles += node(
                    "android.widget.TextView",
                    rid="message_text",
                    text=bubble.body,
                    bounds=(left, top, right, top + 80),
                )
                bubbles += node(
                    "android.widget.TextView",
                    rid="message_status",
                    text=bubble.stamp,
                    bounds=(left, top + 84, right, top + 120),
                )
            body = (
                node(
                    "android.widget.FrameLayout",
                    rid="conversation_messages_recycler_view",
                    bounds=(0, 200, WIDTH, 2080),
                    children=bubbles,
                )
                + node(
                    "android.widget.EditText",
                    rid="compose_message_text",
                    text=self.compose,
                    desc="Text message",
                    bounds=(40, 2100, 880, 2200),
                    clickable=True,
                )
                + node(
                    "android.widget.ImageButton",
                    rid="send_message_button_icon",
                    desc="Send SMS",
                    bounds=(920, 2100, 1040, 2200),
                    clickable=True,
                )
            )
        return (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
            f'<hierarchy rotation="0">'
            f"{node(FRAME, bounds=(0, 0, WIDTH, HEIGHT), children=body)}"
            "</hierarchy>\nUI hierchary dumped to: /sdcard/ng-screen.xml\n"
        )

    # --- test conveniences ---------------------------------------------

    def receive(self, sender: str, body: str, stamp: str = "now") -> None:
        """The other side texts in. Appears on screen, nothing else."""
        thread = self.threads.setdefault(sender, Thread(name=sender))
        thread.bubbles.append(Bubble(body=body, outgoing=False, stamp=stamp))
        self.clock += 1
        thread.row_time = f"{self.clock}m"


def make_phone(**kwargs) -> FakePhone:
    return FakePhone(**kwargs)


__all__ = [
    "FakePhone",
    "Thread",
    "Bubble",
    "make_phone",
    "PACKAGE",
    "WIDTH",
    "HEIGHT",
    "LIST",
    "NEW",
    "THREAD",
]
