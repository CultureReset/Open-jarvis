"""Real-SIM SMS channel: send and receive through a paired physical Android.

Every other SMS channel here routes through somebody else's server — Twilio,
SendBlue, WhatsApp, Signal. This one routes through a phone the owner holds,
using its own SIM and its own number. No provider account, no webhook, no
third party in the path.

Why that matters beyond privacy: the phone becomes a destination. A Walmart
checkout that offers to text a receipt, a restaurant POS, an airline, a
hotel — they all send to a real number, and a real number is the one thing a
cloud SMS API cannot give you cheaply for inbound business mail.

Three rules this adapter keeps, because SMS is used here to authorize real
actions:

**It is bound to one device.** The serial is configured, and connect() refuses
a different phone even if it is the only one plugged in. Otherwise a swapped
cable silently changes which SIM speaks for the owner.

**It never claims delivery.** ``send`` returns True only after the message is
observed in the device's own sent box. A shell command that returned zero is
not evidence a carrier accepted anything, and the difference matters when the
message is an approval request.

**It never invents an inbound message.** Receive reads the device's SMS
provider and dedupes on the provider's own row id, so a poll that overlaps a
previous one cannot replay an approval reply.

Sending needs a path onto the SIM. Two are supported:

``companion``
    The NEXT GENT companion app holds the SMS role and exposes a loopback
    endpoint over the adb tunnel. This is the production path: the SMS role is
    a documented Android capability, survives reboots, and needs no debugging
    surface left open.

``service_call``
    ``adb shell service call isms`` — the development path. The transaction
    code for ``sendTextForSubscriber`` is not stable across Android versions,
    so it is configurable and defaults to the Android 14/15 value. Verify it on
    the target build before trusting it; a wrong code fails loudly rather than
    sending to the wrong recipient.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from openjarvis.channels._stubs import (
    BaseChannel,
    ChannelHandler,
    ChannelMessage,
    ChannelStatus,
)
from openjarvis.core.events import EventBus, EventType
from openjarvis.core.registry import ChannelRegistry

logger = logging.getLogger(__name__)

# service call isms transaction for sendTextForSubscriber. Android 14/15.
DEFAULT_ISMS_TRANSACTION = 5
POLL_SECONDS = 5
E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def _run(argv: List[str], timeout: int = 20) -> subprocess.CompletedProcess:
    """Run a command. Never raises; the caller inspects returncode."""
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


class AdbRunner:
    """Thin shell around adb, bound to one device serial.

    Injectable so the channel is testable without a phone attached.
    """

    def __init__(self, serial: str, adb: str = "adb") -> None:
        self.serial = serial
        self.adb = adb

    def available(self) -> bool:
        return shutil.which(self.adb) is not None

    def devices(self) -> List[str]:
        result = _run([self.adb, "devices"])
        if result.returncode != 0:
            return []
        found = []
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                found.append(parts[0])
        return found

    def shell(self, command: str, timeout: int = 20) -> subprocess.CompletedProcess:
        return _run([self.adb, "-s", self.serial, "shell", command], timeout=timeout)


def parse_sms_rows(output: str) -> List[Dict[str, str]]:
    """Parse `content query --uri content://sms/...` output.

    The provider prints one row per line as `Row: N key=value, key=value`.
    A value containing a comma would break naive splitting, so the body is
    taken as everything after `body=` up to the next `, <key>=` boundary.
    """
    rows = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("Row:"):
            continue
        fields: Dict[str, str] = {}
        for match in re.finditer(r"(\w+)=(.*?)(?=, \w+=|$)", line.split(" ", 2)[-1]):
            fields[match.group(1)] = match.group(2).strip()
        if fields.get("_id"):
            rows.append(fields)
    return rows


@ChannelRegistry.register("android_sim")
class AndroidSimChannel(BaseChannel):
    """SMS over a paired physical Android's own SIM."""

    channel_id = "android_sim"

    def __init__(
        self,
        *,
        serial: str = "",
        own_number: str = "",
        send_mode: str = "",
        companion_port: int = 0,
        isms_transaction: int = 0,
        runner: Optional[AdbRunner] = None,
        poll_seconds: int = POLL_SECONDS,
        bus: Optional[EventBus] = None,
    ) -> None:
        self._serial = serial or os.environ.get("NG_ANDROID_SERIAL", "")
        self._own_number = own_number or os.environ.get("NG_AGENT_NUMBER", "")
        self._send_mode = send_mode or os.environ.get("NG_SMS_SEND_MODE", "companion")
        self._companion_port = companion_port or int(os.environ.get("NG_COMPANION_PORT", "8767"))
        self._isms_transaction = isms_transaction or int(
            os.environ.get("NG_ISMS_TRANSACTION", DEFAULT_ISMS_TRANSACTION))
        self._runner = runner or AdbRunner(self._serial)
        self._poll_seconds = poll_seconds
        self._bus = bus

        self._handlers: List[ChannelHandler] = []
        self._status = ChannelStatus.DISCONNECTED
        self._seen: set[str] = set()
        self._high_water = 0
        self._poller: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # --- lifecycle ------------------------------------------------------

    def connect(self) -> None:
        """Attach to the configured device, or refuse.

        Refusing is the point. A channel that authorizes spending must not
        follow whichever phone happens to be plugged in.
        """
        self._status = ChannelStatus.CONNECTING
        if not self._serial:
            logger.error("No device serial configured; set NG_ANDROID_SERIAL")
            self._status = ChannelStatus.ERROR
            return
        if not self._own_number or not E164.match(self._own_number):
            logger.error("Agent number must be configured in E.164 form")
            self._status = ChannelStatus.ERROR
            return
        if not self._runner.available():
            logger.error("adb not found on PATH")
            self._status = ChannelStatus.ERROR
            return

        attached = self._runner.devices()
        if self._serial not in attached:
            logger.error(
                "Paired device %s is not attached (attached: %s). Refusing to use another phone.",
                self._serial, ", ".join(attached) or "none")
            self._status = ChannelStatus.ERROR
            return

        if not self.sim_ready():
            logger.error("Device %s has no ready SIM", self._serial)
            self._status = ChannelStatus.ERROR
            return

        self._high_water = self._latest_inbox_id()
        self._status = ChannelStatus.CONNECTED
        self._start_polling()
        logger.info("Real-SIM channel attached to %s as %s", self._serial, self._own_number)

    def disconnect(self) -> None:
        self._stop.set()
        if self._poller and self._poller.is_alive():
            self._poller.join(timeout=self._poll_seconds + 2)
        self._poller = None
        self._status = ChannelStatus.DISCONNECTED

    def status(self) -> ChannelStatus:
        return self._status

    def list_channels(self) -> List[str]:
        return [self._own_number] if self._own_number else []

    def on_message(self, handler: ChannelHandler) -> None:
        self._handlers.append(handler)

    # --- device state ---------------------------------------------------

    def sim_ready(self) -> bool:
        result = self._runner.shell("getprop gsm.sim.state")
        return result.returncode == 0 and "READY" in result.stdout.upper()

    def health(self) -> Dict[str, Any]:
        """What the owner's device page needs. Absence is reported, not guessed."""
        return {
            "serial": self._serial,
            "number": self._own_number,
            "attached": self._serial in self._runner.devices(),
            "sim_ready": self.sim_ready(),
            "send_mode": self._send_mode,
            "status": self._status.value,
        }

    # --- sending --------------------------------------------------------

    def send(
        self,
        channel: str,
        content: str,
        *,
        conversation_id: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> bool:
        """Send through the SIM. True only once the device's sent box shows it."""
        if self._status is not ChannelStatus.CONNECTED:
            logger.error("Real-SIM channel is not connected")
            return False
        if not E164.match(channel or ""):
            logger.error("Recipient must be an E.164 number, got %r", channel)
            return False
        if not content.strip():
            logger.error("Refusing to send an empty message")
            return False

        sender = self._companion_send if self._send_mode == "companion" else self._service_call_send
        accepted = sender(channel, content)
        if not accepted:
            return False

        if self._observe_sent(channel, content):
            self._publish_sent(channel, content, conversation_id)
            return True

        # The command returned without error but nothing is in the sent box.
        # That is an uncertain outcome, not a success and not a clean failure;
        # say so rather than letting a caller assume the owner was reached.
        logger.warning(
            "Message to %s was accepted by the device but is not visible in its sent box; "
            "treat delivery as uncertain and reconcile before resending", channel)
        if self._bus:
            self._bus.publish(EventType.CHANNEL_MESSAGE_SENT,
                              {"channel": self.channel_id, "to": channel,
                               "delivery": "uncertain", "conversation_id": conversation_id})
        return False

    def _companion_send(self, to: str, content: str) -> bool:
        """Hand the message to the companion app, which holds the SMS role."""
        import json
        import urllib.error
        import urllib.request

        forward = self._runner.shell("echo ok")
        if forward.returncode != 0:
            logger.error("Device is unreachable over adb")
            return False
        payload = json.dumps({"to": to, "body": content}).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{self._companion_port}/sms/send",
            data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return 200 <= response.status < 300
        except (urllib.error.URLError, OSError) as exc:
            logger.error(
                "Companion app is not reachable on port %s (%s). Install the companion app or "
                "set NG_SMS_SEND_MODE=service_call for development.", self._companion_port, exc)
            return False

    def _service_call_send(self, to: str, content: str) -> bool:
        """Development path. The transaction code is version-specific."""
        packed = " ".join(f"s16 {part!r}" for part in ("", to, ""))
        command = (
            f"service call isms {self._isms_transaction}"
            f" i32 1 {packed} s16 {content!r} s16 '' s16 ''"
        )
        result = self._runner.shell(command, timeout=30)
        if result.returncode != 0 or "Result: Parcel" not in result.stdout:
            logger.error(
                "service call isms %s failed. The transaction code differs across Android "
                "builds; verify it on this device and set NG_ISMS_TRANSACTION. stderr: %s",
                self._isms_transaction, result.stderr.strip()[:200])
            return False
        return True

    def _observe_sent(self, to: str, content: str, attempts: int = 4) -> bool:
        """Look in the device's own sent box. Evidence, not assumption."""
        digits = re.sub(r"\D", "", to)[-10:]
        for _ in range(attempts):
            result = self._runner.shell(
                "content query --uri content://sms/sent --projection _id:address:body "
                "--sort '_id DESC LIMIT 5'")
            if result.returncode == 0:
                for row in parse_sms_rows(result.stdout):
                    body = row.get("body", "")
                    address = re.sub(r"\D", "", row.get("address", ""))
                    if content[:40] in body and address.endswith(digits):
                        return True
            time.sleep(1)
        return False

    # --- receiving ------------------------------------------------------

    def poll_once(self) -> List[ChannelMessage]:
        """Read new inbound messages. Deduped on the provider's own row id."""
        result = self._runner.shell(
            "content query --uri content://sms/inbox "
            f"--projection _id:address:body:date --where '_id > {self._high_water}' "
            "--sort '_id ASC LIMIT 50'")
        if result.returncode != 0:
            logger.warning("Could not read the device inbox: %s", result.stderr.strip()[:200])
            return []

        received = []
        for row in parse_sms_rows(result.stdout):
            row_id = row["_id"]
            if row_id in self._seen:
                continue
            self._seen.add(row_id)
            try:
                self._high_water = max(self._high_water, int(row_id))
            except ValueError:
                continue
            message = ChannelMessage(
                channel=self.channel_id,
                sender=row.get("address", ""),
                content=row.get("body", ""),
                message_id=f"{self._serial}:{row_id}",
                conversation_id=row.get("address", ""),
                metadata={"received_on": self._own_number, "device_row": row_id,
                          "device_date": row.get("date", ""), "transport": "real_sim",
                          "evidence": f"content://sms/inbox/{row_id}"},
            )
            received.append(message)
        return received

    def _dispatch(self, message: ChannelMessage) -> None:
        for handler in self._handlers:
            try:
                handler(message)
            except Exception:
                logger.exception("A channel handler raised on message %s", message.message_id)
        if self._bus:
            self._bus.publish(EventType.CHANNEL_MESSAGE_RECEIVED, {
                "channel": self.channel_id, "sender": message.sender,
                "content": message.content, "message_id": message.message_id,
                "transport": "real_sim",
            })

    def _start_polling(self) -> None:
        self._stop.clear()

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    for message in self.poll_once():
                        self._dispatch(message)
                except Exception:
                    logger.exception("Inbox poll failed; continuing")
                self._stop.wait(self._poll_seconds)

        self._poller = threading.Thread(target=loop, name="android-sim-inbox", daemon=True)
        self._poller.start()

    def _latest_inbox_id(self) -> int:
        result = self._runner.shell(
            "content query --uri content://sms/inbox --projection _id --sort '_id DESC LIMIT 1'")
        if result.returncode != 0:
            return 0
        rows = parse_sms_rows(result.stdout)
        try:
            return int(rows[0]["_id"]) if rows else 0
        except (ValueError, KeyError):
            return 0

    def _publish_sent(self, to: str, content: str, conversation_id: str) -> None:
        if self._bus:
            self._bus.publish(EventType.CHANNEL_MESSAGE_SENT, {
                "channel": self.channel_id, "to": to, "content": content,
                "delivery": "observed_in_sent_box", "conversation_id": conversation_id,
            })


__all__ = ["AndroidSimChannel", "AdbRunner", "parse_sms_rows"]
