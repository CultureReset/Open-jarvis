"""Texting by working the Messages app on screen.

The agent does what a person does. It opens Messages, starts a conversation,
types the number, types the words, and taps send. Then it looks at the screen
to see whether the message is actually there. Replies are read off the thread.

Nothing in here knows an app-specific view name; that is all in the App Map.
What is in here is the procedure and its evidence rules:

**Typed is not the same as intended.** ``input text`` cannot represent every
character. So the body is typed and then read back out of the compose field
and compared to what was asked for. A mismatch abandons the send — a garbled
message is bad; a garbled authorization request is worse.

**Tapped send is not the same as sent.** ``send`` reports ``sent`` only when
the compose field has emptied *and* the words are visible in an outgoing
bubble in this thread, with no failure marker on screen. Anything else is
``uncertain``, which is reported as uncertain and never as success.

**A reply is only what the screen shows.** Inbound messages come from reading
bubbles, and are aligned against what was read last time, so a poll that
overlaps a previous one cannot replay an approval reply. Where the alignment
cannot be established the procedure yields nothing rather than guessing.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from openjarvis.phone.appmap import AppMap
from openjarvis.phone.device import PhoneDevice
from openjarvis.phone.uitree import UiNode, find, find_all

logger = logging.getLogger(__name__)

E164 = re.compile(r"^\+[1-9]\d{6,14}$")

SENT = "sent"
NOT_SENT = "not_sent"
UNCERTAIN = "uncertain"


@dataclass
class SendOutcome:
    """What the screen showed after trying to send."""

    status: str
    to: str
    body: str
    evidence: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == SENT

    def note(self, line: str) -> "SendOutcome":
        self.evidence.append(line)
        return self


@dataclass(frozen=True)
class ScreenMessage:
    """One bubble, as read."""

    conversation: str
    body: str
    outgoing: bool
    timestamp_text: str = ""

    @property
    def fingerprint(self) -> str:
        raw = "\x1f".join(
            (
                self.conversation,
                "out" if self.outgoing else "in",
                self.body,
                self.timestamp_text,
            )
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class ConversationRow:
    """One row of the conversation list."""

    name: str
    preview: str
    node: UiNode

    @property
    def signature(self) -> str:
        return f"{self.name}\x1f{self.preview}"


def align_new(previous: Sequence[str], current: Sequence[str]) -> Tuple[int, str]:
    """Where the new messages start in ``current``.

    The two reads overlap: the screen still shows most of what it showed last
    time. Find the longest tail of ``previous`` that is a head of ``current``
    and everything after it is new.

    Returns the index into ``current`` where new messages begin, and a note
    for the log. When no overlap can be found and there *was* previous state,
    the index is ``len(current)`` — nothing is emitted. That is deliberate:
    the thread may have scrolled past the overlap, and re-emitting an old
    "YES" would re-authorize a spend.
    """
    if not current:
        return 0, "nothing on screen"
    if not previous:
        return 0, "first read; caller decides whether this is a baseline"
    for overlap in range(min(len(previous), len(current)), 0, -1):
        if list(previous[-overlap:]) == list(current[:overlap]):
            return overlap, f"aligned on {overlap} message(s) of overlap"
    return len(current), (
        "no overlap with the previous read; emitting nothing rather than "
        "risking a replay"
    )


class MessagesProcedure:
    """Drive one Messages app through its App Map."""

    def __init__(
        self,
        device: PhoneDevice,
        app_map: AppMap,
        *,
        step_pause: float = 0.4,
        verify_attempts: int = 5,
        observe_pause: float = 1.0,
    ) -> None:
        self.device = device
        self.map = app_map
        self.step_pause = step_pause
        self.verify_attempts = verify_attempts
        self.observe_pause = observe_pause
        self._width = 0

    # --- helpers --------------------------------------------------------

    def _look(self, element: str, timeout: float = 6.0) -> Optional[UiNode]:
        selectors = self.map.selectors(element)
        return self.device.look_for(*selectors, timeout=timeout) if selectors else None

    def _on_screen(self, screen: Optional[UiNode], element: str) -> Optional[UiNode]:
        selectors = self.map.selectors(element)
        return find(screen, *selectors) if selectors else None

    def _screen_width(self) -> int:
        if not self._width:
            size = self.device.screen_size()
            self._width = size[0] if size else 0
        return self._width

    def _dismiss_permission_prompt(self, screen: Optional[UiNode]) -> bool:
        """Tap a system Allow prompt if one is covering the app.

        Only the app's own runtime prompts; nothing here grants a permission
        the owner has not been shown.
        """
        if not self.map.has("permission_allow"):
            return False
        node = self._on_screen(screen, "permission_allow")
        if node is None:
            return False
        logger.info("A permission prompt is covering Messages; confirming it on screen")
        return self.device.tap_node(node)

    # --- navigation -----------------------------------------------------

    def open_app(self) -> bool:
        """Open Messages and confirm from the screen that it is open."""
        if not self.device.open_app(self.map.package, self.map.launch_activity):
            logger.error("Could not open %s", self.map.package)
            return False
        screen = self.device.screen()
        self._dismiss_permission_prompt(screen)
        if self._on_screen(screen, "conversation_list_anchor") is not None:
            return True
        if self._on_screen(screen, "thread_anchor") is not None:
            # Opened straight into the last thread. Back out to the list.
            self.device.back()
            return self._look("conversation_list_anchor") is not None
        return self._look("conversation_list_anchor") is not None

    def at_conversation_list(self) -> bool:
        return (
            self._on_screen(self.device.screen(), "conversation_list_anchor")
            is not None
        )

    def ensure_conversation_list(self, attempts: int = 3) -> bool:
        """Get back to the list of conversations from wherever we are."""
        for _ in range(attempts):
            if self.at_conversation_list():
                return True
            self.device.back()
            time.sleep(self.step_pause)
        return self.open_app()

    def list_conversations(self) -> List[ConversationRow]:
        """Read the conversation list off the screen.

        The name comes from the row's own label; the preview is the rest of
        the text in the row, which is how a change in a conversation is
        noticed without opening it.
        """
        screen = self.device.screen()
        rows = []
        for name_node in find_all(screen, *self.map.selectors("conversation_row")):
            host = name_node.nearest_clickable()
            others = [
                node.label
                for node in host.walk()
                if node is not name_node
                and node.label
                and node.label != name_node.label
            ]
            rows.append(
                ConversationRow(
                    name=name_node.label, preview=" | ".join(others[:3]), node=host
                )
            )
        return rows

    def open_conversation(self, name: str) -> bool:
        """Open an existing conversation by the name shown on its row."""
        wanted = _comparable(name)
        for row in self.list_conversations():
            if _comparable(row.name) == wanted:
                if not self.device.tap_node(row.node):
                    return False
                return self._look("thread_anchor") is not None
        return False

    # --- composing ------------------------------------------------------

    def start_new_conversation(self, to: str) -> bool:
        """Tap 'start chat', type the number, and land in its thread."""
        button = self._look("start_new_conversation")
        if button is None:
            logger.error("Could not find the start-a-conversation control on screen")
            return False
        if not self.device.tap_node(button):
            return False

        recipient = self._look("recipient_field")
        if recipient is None:
            logger.error("The new-conversation screen did not show a recipient field")
            return False
        if not self.device.tap_node(recipient):
            return False
        if not self.device.type_text(to):
            return False

        typed = self._read_field("recipient_field")
        if _digits(typed) != _digits(to):
            logger.error(
                "The recipient field reads %r after typing %r; abandoning rather than "
                "messaging an unintended number",
                typed,
                to,
            )
            return False

        commit = (
            self._on_screen(self.device.screen(), "recipient_commit")
            if self.map.has("recipient_commit")
            else None
        )
        if commit is not None:
            self.device.tap_node(commit)
        else:
            # No confirm control on this build's screen; the keyboard's enter
            # commits the recipient, which is what a person does here.
            self.device.press("KEYCODE_ENTER")

        return self._look("compose_field") is not None

    def _read_field(self, element: str) -> str:
        node = self._on_screen(self.device.screen(), element)
        return node.text if node is not None else ""

    def type_body(self, body: str) -> bool:
        """Type the message and confirm the field holds exactly it."""
        compose = self._look("compose_field")
        if compose is None:
            logger.error("No compose field on screen")
            return False
        if compose.text:
            self.device.tap_node(compose)
            self.device.clear_focused_field(len(compose.text))
        if not self.device.tap_node(compose):
            return False
        if not self.device.type_text(body):
            return False

        for attempt in range(2):
            readback = self._read_field("compose_field")
            if readback == body:
                return True
            logger.warning(
                "The compose field reads %r, not the intended message (attempt %d)",
                readback,
                attempt + 1,
            )
            current = self._look("compose_field")
            if current is None:
                return False
            self.device.tap_node(current)
            self.device.clear_focused_field(len(readback) or len(body))
            if not self.device.type_text(body):
                return False
        final = self._read_field("compose_field")
        if final == body:
            return True
        logger.error(
            "Giving up: the phone's compose field holds %r and the message was to "
            "be %r. Nothing was sent.",
            final,
            body,
        )
        return False

    # --- sending --------------------------------------------------------

    def send(self, to: str, body: str) -> SendOutcome:
        """Text ``to`` by working the screen. Only screen evidence counts."""
        outcome = SendOutcome(status=NOT_SENT, to=to, body=body)
        if not E164.match(to or ""):
            return outcome.note(f"{to!r} is not an E.164 number; nothing typed")
        if not body.strip():
            return outcome.note("refused to send an empty message")

        with self.device.lock:
            if not self.device.attached():
                return outcome.note(f"the phone {self.device.serial} is not attached")
            if not self.open_app():
                return outcome.note("could not get to the Messages conversation list")
            outcome.note("Messages is open at the conversation list")

            if not self.start_new_conversation(to):
                return outcome.note(f"could not open a conversation to {to}")
            outcome.note(
                f"a conversation to {to} is open, recipient confirmed on screen"
            )

            if not self.type_body(body):
                return outcome.note("the compose field never held the intended text")
            outcome.note("the compose field holds exactly the intended text")

            button = self._look("send_button")
            if button is None:
                return outcome.note("no send button on screen")
            if not self.device.tap_node(button):
                return outcome.note("the send button did not take the tap")
            outcome.note("send tapped")

            return self._observe_send(outcome)

    def _observe_send(self, outcome: SendOutcome) -> SendOutcome:
        """Look at the thread to see whether the message is actually there."""
        for _ in range(self.verify_attempts):
            screen = self.device.screen()
            if self.map.has("send_failed"):
                failure = self._on_screen(screen, "send_failed")
                if failure is not None:
                    outcome.status = NOT_SENT
                    return outcome.note(
                        f"the thread shows {failure.label!r}; the phone did not send it"
                    )
            compose_empty = not (self._read_field("compose_field") or "")
            bubbles = self._read_bubbles(screen, conversation=outcome.to)
            landed = any(
                message.outgoing and message.body.strip() == outcome.body.strip()
                for message in bubbles
            )
            if compose_empty and landed:
                outcome.status = SENT
                return outcome.note(
                    "the compose field is empty and the message is visible in an "
                    "outgoing bubble in this thread"
                )
            time.sleep(self.observe_pause)

        outcome.status = UNCERTAIN
        return outcome.note(
            "send was tapped but the message is not visible in an outgoing bubble; "
            "treat delivery as uncertain and reconcile before resending"
        )

    # --- reading --------------------------------------------------------

    def _read_bubbles(
        self, screen: Optional[UiNode], conversation: str
    ) -> List[ScreenMessage]:
        width = self._screen_width()
        stamps = (
            find_all(screen, *self.map.selectors("bubble_timestamp"))
            if self.map.has("bubble_timestamp")
            else []
        )
        messages = []
        for bubble in find_all(screen, *self.map.selectors("message_bubble")):
            if not bubble.label:
                continue
            nearest = ""
            for stamp in stamps:
                if stamp.order > bubble.order:
                    nearest = stamp.label
                    break
            messages.append(
                ScreenMessage(
                    conversation=conversation,
                    body=bubble.label,
                    outgoing=self.map.is_outgoing(bubble, width),
                    timestamp_text=nearest,
                )
            )
        return messages

    def read_open_thread(self, conversation: str) -> List[ScreenMessage]:
        """Every bubble visible in the thread that is currently open."""
        with self.device.lock:
            return self._read_bubbles(self.device.screen(), conversation)

    def read_conversation(self, name: str) -> List[ScreenMessage]:
        """Open a conversation and read what is on its screen."""
        with self.device.lock:
            if not self.ensure_conversation_list():
                return []
            if not self.open_conversation(name):
                logger.warning("No conversation named %r on the list", name)
                return []
            messages = self._read_bubbles(self.device.screen(), name)
            self.device.back()
            return messages


class InboxWatcher:
    """New inbound messages, by watching the conversation list change.

    The list shows each conversation's latest line — its name, its newest
    message and the time label the app puts on the row. When that line
    changes, the thread is opened, read, and aligned against the last read of
    that thread. No database, no notification hook: the same cue a person
    gets from glancing at the screen.

    The limit is the cue itself. A message is noticed because the row line
    changed, so an app whose row line does not change for a new message would
    hold that message until the next change. In practice the row's own time
    label moves on every message, which is what makes the cue reliable; it is
    worth re-checking during App Map calibration on the real phone, since it
    is a property of the app, not of this code.
    """

    def __init__(self, procedure: MessagesProcedure, prime_limit: int = 12) -> None:
        self.procedure = procedure
        self.prime_limit = prime_limit
        self._row_signatures: Dict[str, str] = {}
        self._thread_reads: Dict[str, List[str]] = {}
        self._known_threads: set[str] = set()
        self.baselined = False

    def baseline(self) -> int:
        """Record what is already there without emitting any of it.

        Each conversation on the list is opened and read once, so the next
        poll has something to align against. Without that, the first reply to
        arrive after connecting is indistinguishable from thread history and
        would be dropped — and the first reply is usually the approval.
        """
        with self.procedure.device.lock:
            if not self.procedure.open_app():
                logger.error("Could not baseline the inbox: Messages would not open")
                return 0
            rows = self.procedure.list_conversations()
            self._row_signatures = {row.name: row.signature for row in rows}
            self._known_threads = {row.name for row in rows}
            for row in rows[: self.prime_limit]:
                self._prime(row.name)
            if len(rows) > self.prime_limit:
                logger.info(
                    "%d conversation(s) beyond the first %d were not read at baseline; "
                    "a change in one of those will be recorded rather than emitted",
                    len(rows) - self.prime_limit,
                    self.prime_limit,
                )
            self.baselined = True
            logger.info(
                "Inbox baselined on %d conversation(s) already on screen", len(rows)
            )
            return len(rows)

    def poll(self) -> List[ScreenMessage]:
        """Glance at the list; read the threads whose latest line changed."""
        with self.procedure.device.lock:
            if not self.procedure.ensure_conversation_list():
                return []
            rows = self.procedure.list_conversations()
            changed = [
                row
                for row in rows
                if self._row_signatures.get(row.name) != row.signature
            ]
            if not self.baselined:
                logger.info(
                    "Inbox was not baselined; treating this poll as the baseline so "
                    "existing conversations are not replayed as new"
                )
                self._row_signatures = {row.name: row.signature for row in rows}
                self._known_threads = {row.name for row in rows}
                self.baselined = True
                for row in rows[: self.prime_limit]:
                    self._prime(row.name)
                return []

            for row in rows:
                self._row_signatures[row.name] = row.signature
            fresh: List[ScreenMessage] = []
            for row in changed:
                fresh.extend(self._read_new_in(row.name))
            self._known_threads.update(row.name for row in rows)
            return fresh

    def _prime(self, name: str) -> None:
        messages = self.procedure.read_conversation(name)
        self._thread_reads[name] = [message.fingerprint for message in messages]
        self._known_threads.add(name)

    def _read_new_in(self, name: str) -> List[ScreenMessage]:
        first_time = name not in self._thread_reads
        brand_new = name not in self._known_threads
        messages = self.procedure.read_conversation(name)
        current = [message.fingerprint for message in messages]
        previous = self._thread_reads.get(name, [])
        start, note = align_new(previous, current)
        self._thread_reads[name] = current

        if first_time and brand_new:
            # A conversation that did not exist at the last glance. Nothing in
            # it can have been reported before, so all of it is new.
            logger.info(
                "New conversation with %s; %d bubble(s) on screen", name, len(messages)
            )
            return [message for message in messages if not message.outgoing]
        if first_time:
            logger.info(
                "%s was on the list but had not been read; recording it rather than "
                "emitting history as new",
                name,
            )
            return []
        if start >= len(current):
            logger.info("Nothing new in %s (%s)", name, note)
            return []
        logger.info("%d new bubble(s) in %s (%s)", len(current) - start, name, note)
        return [message for message in messages[start:] if not message.outgoing]


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _comparable(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip().casefold()


__all__ = [
    "MessagesProcedure",
    "InboxWatcher",
    "SendOutcome",
    "ScreenMessage",
    "ConversationRow",
    "align_new",
    "SENT",
    "NOT_SENT",
    "UNCERTAIN",
    "E164",
]
