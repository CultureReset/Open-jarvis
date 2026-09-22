"""Real-SIM SMS channel: the agent works the phone's screen.

Every other SMS channel here routes through somebody else's server — Twilio,
SendBlue, WhatsApp, Signal. This one routes through a phone that is part of
the box, using its own SIM and its own number. No provider account, no
webhook, no third party in the path.

It also uses no send API and no message database. The agent opens Messages,
taps the controls, types the words and taps send, then looks at the screen to
see whether the message is there. Replies are read off the thread. The
mechanics live in :mod:`openjarvis.phone`, where :class:`ScreenOnlyShell`
refuses any command that is not a screen verb, so ``service call isms`` and
``content://sms`` cannot be issued from here even by accident.

This channel is the thin part: it binds to one device, wires the procedure to
OpenJarvis's channel contract, and keeps three rules, because SMS is used
here to authorize real actions.

**It is bound to one device.** The serial is configured, and connect() refuses
a different phone even if it is the only one plugged in. Otherwise a swapped
cable silently changes which SIM speaks for the owner.

**It never claims delivery.** ``send`` returns True only when the words were
seen in an outgoing bubble in the thread. A tap that landed is not evidence
that a message exists, and the difference matters when the message is an
approval request.

**It never invents an inbound message.** Inbound comes from reading the
thread and aligning against the previous read, so an overlapping poll cannot
replay an approval reply. Where the alignment cannot be established, nothing
is emitted.

Configuration:

``NG_ANDROID_SERIAL``
    The adb serial of the phone that belongs to this box. Required.
``NG_AGENT_NUMBER``
    That phone's own number, E.164. Required, and checked, so the channel can
    say which number spoke.
``NG_MESSAGES_APP_MAP``
    An App Map id shipped in ``openjarvis/phone/data`` or a path to a TOML
    file. Defaults to ``google_messages``.
``NG_APPMAP_CALIBRATING``
    Set to 1 only while calibrating an App Map against a real device. An
    unvalidated map is otherwise refused: unconfirmed selectors on a live
    phone are how a message reaches the wrong conversation.
``NG_SMS_POLL_SECONDS``
    How often to glance at the conversation list. Default 20s — reading the
    screen takes the screen, so this is deliberately not a busy loop.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from openjarvis.channels._stubs import (
    BaseChannel,
    ChannelHandler,
    ChannelMessage,
    ChannelStatus,
)
from openjarvis.core.events import EventBus, EventType
from openjarvis.core.registry import ChannelRegistry
from openjarvis.phone.appmap import (
    AppMap,
    AppMapError,
    builtin_map_path,
    load_app_map,
)
from openjarvis.phone.device import PhoneDevice, ScreenOnlyShell
from openjarvis.phone.messages import (
    E164,
    SENT,
    UNCERTAIN,
    InboxWatcher,
    MessagesProcedure,
    ScreenMessage,
)

logger = logging.getLogger(__name__)

POLL_SECONDS = 20
DEFAULT_APP_MAP = "google_messages"


def resolve_app_map(reference: str, *, calibrating: bool = False) -> AppMap:
    """Load an App Map by shipped id or by path."""
    candidate = Path(reference)
    path = candidate if candidate.suffix == ".toml" else builtin_map_path(reference)
    return load_app_map(path, calibrating=calibrating)


@ChannelRegistry.register("android_sim")
class AndroidSimChannel(BaseChannel):
    """SMS over the box's own phone, driven through its screen."""

    channel_id = "android_sim"

    def __init__(
        self,
        *,
        serial: str = "",
        own_number: str = "",
        app_map: str | AppMap = "",
        calibrating: Optional[bool] = None,
        device: Optional[PhoneDevice] = None,
        procedure: Optional[MessagesProcedure] = None,
        poll_seconds: int = POLL_SECONDS,
        bus: Optional[EventBus] = None,
    ) -> None:
        self._serial = serial or os.environ.get("NG_ANDROID_SERIAL", "")
        self._own_number = own_number or os.environ.get("NG_AGENT_NUMBER", "")
        self._app_map_ref = app_map or os.environ.get(
            "NG_MESSAGES_APP_MAP", DEFAULT_APP_MAP
        )
        self._calibrating = (
            calibrating
            if calibrating is not None
            else os.environ.get("NG_APPMAP_CALIBRATING", "") in ("1", "true", "yes")
        )
        self._poll_seconds = poll_seconds or int(
            os.environ.get("NG_SMS_POLL_SECONDS", POLL_SECONDS)
        )

        self._device = device
        self._procedure = procedure
        self._watcher: Optional[InboxWatcher] = None
        self._map: Optional[AppMap] = app_map if isinstance(app_map, AppMap) else None
        self._map_error = ""

        self._bus = bus
        self._handlers: List[ChannelHandler] = []
        self._status = ChannelStatus.DISCONNECTED
        self._poller: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # --- lifecycle ------------------------------------------------------

    def connect(self) -> None:
        """Attach to the configured device and App Map, or refuse.

        Refusing is the point. A channel that authorizes spending must not
        follow whichever phone happens to be plugged in, and must not drive a
        screen with selectors nobody has confirmed.
        """
        self._status = ChannelStatus.CONNECTING
        if not self._serial:
            return self._fail("No device serial configured; set NG_ANDROID_SERIAL")
        if not self._own_number or not E164.match(self._own_number):
            return self._fail("The phone's own number must be configured in E.164 form")

        if self._map is None:
            try:
                self._map = resolve_app_map(
                    str(self._app_map_ref), calibrating=self._calibrating
                )
            except AppMapError as exc:
                self._map_error = str(exc)
                return self._fail(str(exc))

        if self._device is None:
            self._device = PhoneDevice(self._serial, ScreenOnlyShell(self._serial))
        if not self._device.shell.available():
            return self._fail("adb not found on PATH")

        attached = self._device.shell.devices()
        if self._serial not in attached:
            return self._fail(
                f"The box's phone {self._serial} is not attached (attached: "
                f"{', '.join(attached) or 'none'}). Refusing to use another phone."
            )
        if not self._device.sim_ready():
            return self._fail(f"The phone {self._serial} has no ready SIM")

        if self._procedure is None:
            self._procedure = MessagesProcedure(self._device, self._map)
        self._watcher = InboxWatcher(self._procedure)
        self._watcher.baseline()

        self._status = ChannelStatus.CONNECTED
        self._start_polling()
        logger.info(
            "Real-SIM channel attached to %s as %s, driving %s through App Map %s",
            self._serial,
            self._own_number,
            self._map.package,
            self._map.id,
        )

    def _fail(self, reason: str) -> None:
        logger.error("%s", reason)
        self._status = ChannelStatus.ERROR

    def disconnect(self) -> None:
        self._stop.set()
        if self._poller and self._poller.is_alive():
            self._poller.join(timeout=self._poll_seconds + 5)
        self._poller = None
        self._status = ChannelStatus.DISCONNECTED

    def status(self) -> ChannelStatus:
        return self._status

    def list_channels(self) -> List[str]:
        return [self._own_number] if self._own_number else []

    def on_message(self, handler: ChannelHandler) -> None:
        self._handlers.append(handler)

    # --- device state ---------------------------------------------------

    def health(self) -> Dict[str, Any]:
        """What the owner's device page needs. Absence is reported, not guessed."""
        app_map = self._map or self._describe_map()
        report: Dict[str, Any] = {
            "serial": self._serial,
            "number": self._own_number,
            "status": self._status.value,
            "transport": "screen",
            "app_map": app_map.id if app_map else str(self._app_map_ref),
            "app_map_validated": bool(app_map and app_map.validated),
            "app_map_confirmed_against": app_map.validated_on if app_map else "",
            "attached": False,
            "sim_ready": False,
        }
        if self._map_error:
            report["app_map_error"] = self._map_error
        if self._device is not None:
            report["attached"] = self._device.attached()
            report["sim_ready"] = (
                self._device.sim_ready() if report["attached"] else False
            )
        return report

    def _describe_map(self) -> Optional[AppMap]:
        """Read the configured map for reporting only.

        The health endpoint is asked before the channel connects, and the
        answer the owner needs is whether the map has been confirmed against
        a phone. Loading it here is for reporting; the gate that decides
        whether it may drive the screen stays in connect().
        """
        try:
            return resolve_app_map(str(self._app_map_ref), calibrating=True)
        except AppMapError as exc:
            self._map_error = self._map_error or str(exc)
            return None

    # --- sending --------------------------------------------------------

    def send(
        self,
        channel: str,
        content: str,
        *,
        conversation_id: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> bool:
        """Text through the phone's screen. True only on screen evidence."""
        if self._status is not ChannelStatus.CONNECTED or self._procedure is None:
            logger.error("Real-SIM channel is not connected")
            return False

        outcome = self._procedure.send(channel, content)
        if self._bus:
            self._bus.publish(
                EventType.CHANNEL_MESSAGE_SENT,
                {
                    "channel": self.channel_id,
                    "to": channel,
                    "content": content,
                    "delivery": outcome.status,
                    "evidence": outcome.evidence,
                    "conversation_id": conversation_id,
                    "transport": "screen",
                },
            )
        if outcome.status == SENT:
            return True
        if outcome.status == UNCERTAIN:
            logger.warning(
                "Message to %s is uncertain: %s. Reconcile before resending.",
                channel,
                "; ".join(outcome.evidence[-2:]),
            )
        else:
            logger.error(
                "Message to %s was not sent: %s",
                channel,
                "; ".join(outcome.evidence[-2:]),
            )
        return False

    # --- receiving ------------------------------------------------------

    def poll_once(self) -> List[ChannelMessage]:
        """Glance at the screen for new inbound messages."""
        if self._watcher is None:
            return []
        return [self._as_channel_message(seen) for seen in self._watcher.poll()]

    def _as_channel_message(self, seen: ScreenMessage) -> ChannelMessage:
        return ChannelMessage(
            channel=self.channel_id,
            sender=seen.conversation,
            content=seen.body,
            message_id=f"{self._serial}:{seen.fingerprint}",
            conversation_id=seen.conversation,
            metadata={
                "received_on": self._own_number,
                "transport": "screen",
                "evidence": "read from the thread on the phone's screen",
                "screen_timestamp": seen.timestamp_text,
                "fingerprint": seen.fingerprint,
            },
        )

    def _dispatch(self, message: ChannelMessage) -> None:
        for handler in self._handlers:
            try:
                handler(message)
            except Exception:
                logger.exception(
                    "A channel handler raised on message %s", message.message_id
                )
        if self._bus:
            self._bus.publish(
                EventType.CHANNEL_MESSAGE_RECEIVED,
                {
                    "channel": self.channel_id,
                    "sender": message.sender,
                    "content": message.content,
                    "message_id": message.message_id,
                    "transport": "screen",
                },
            )

    def _start_polling(self) -> None:
        self._stop.clear()

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    for message in self.poll_once():
                        self._dispatch(message)
                except Exception:
                    logger.exception("Reading the phone's screen failed; continuing")
                self._stop.wait(self._poll_seconds)

        self._poller = threading.Thread(
            target=loop, name="android-sim-screen", daemon=True
        )
        self._poller.start()


__all__ = ["AndroidSimChannel", "resolve_app_map", "POLL_SECONDS", "DEFAULT_APP_MAP"]
