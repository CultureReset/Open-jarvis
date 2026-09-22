"""Real-SIM channel tests. A fake adb stands in for the phone.

Everything here runs with no device attached. What cannot be tested without
hardware is the transaction code on a specific Android build, and the channel
says so in its own logs rather than pretending.
"""

from __future__ import annotations

import subprocess

import pytest

from openjarvis.channels._stubs import ChannelStatus
from openjarvis.channels.android_sim import AndroidSimChannel, parse_sms_rows

SERIAL = "test-only-serial"
AGENT = "+15550000002"
OWNER = "+15550000001"


def done(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class FakeAdb:
    """Records shell commands and replays canned provider output."""

    def __init__(self, attached=(SERIAL,), sim="READY", inbox=None, sent=None, fail=()):
        self.attached = list(attached)
        self.sim = sim
        self.inbox = inbox if inbox is not None else []
        self.sent = sent if sent is not None else []
        self.fail = set(fail)
        self.commands: list[str] = []
        self.serial = SERIAL

    def available(self) -> bool:
        return "adb" not in self.fail

    def devices(self):
        return list(self.attached)

    def shell(self, command: str, timeout: int = 20):
        self.commands.append(command)
        if "getprop gsm.sim.state" in command:
            return done(self.sim)
        if "content://sms/inbox" in command:
            if "inbox" in self.fail:
                return done(returncode=1, stderr="permission denied")
            return done(_rows(self.inbox))
        if "content://sms/sent" in command:
            return done(_rows(self.sent))
        if "service call isms" in command:
            if "send" in self.fail:
                return done(returncode=1, stderr="service not found")
            return done("Result: Parcel(00000000 00000001 '........')")
        return done("ok")


def _rows(rows):
    return "\n".join(
        f"Row: {i} " + ", ".join(f"{k}={v}" for k, v in row.items())
        for i, row in enumerate(rows))


def channel(adb, **kwargs):
    return AndroidSimChannel(serial=SERIAL, own_number=AGENT, send_mode="service_call",
                             runner=adb, poll_seconds=3600, **kwargs)


# --- parsing -----------------------------------------------------------

def test_provider_rows_parse_including_commas_in_a_body():
    output = _rows([{"_id": "7", "address": OWNER, "body": "YES, do it, please"}])
    rows = parse_sms_rows(output)
    assert len(rows) == 1
    assert rows[0]["_id"] == "7"
    assert rows[0]["body"] == "YES, do it, please"


def test_non_row_output_is_ignored():
    assert parse_sms_rows("No result found.\nrandom noise") == []


# --- device binding ----------------------------------------------------

def test_it_refuses_a_phone_that_is_not_the_paired_one():
    """A swapped cable must not silently change which SIM speaks for the owner."""
    adb = FakeAdb(attached=("some-other-phone",))
    sim = channel(adb)
    sim.connect()
    assert sim.status() is ChannelStatus.ERROR


def test_it_refuses_when_no_serial_is_configured():
    sim = AndroidSimChannel(serial="", own_number=AGENT, runner=FakeAdb())
    sim.connect()
    assert sim.status() is ChannelStatus.ERROR


def test_it_refuses_a_number_that_is_not_e164():
    for number in ("5550000002", "not-a-number", ""):
        sim = AndroidSimChannel(serial=SERIAL, own_number=number, runner=FakeAdb())
        sim.connect()
        assert sim.status() is ChannelStatus.ERROR, number


def test_it_refuses_without_a_ready_sim():
    sim = channel(FakeAdb(sim="ABSENT"))
    sim.connect()
    assert sim.status() is ChannelStatus.ERROR


def test_it_refuses_when_adb_is_missing():
    sim = channel(FakeAdb(fail=("adb",)))
    sim.connect()
    assert sim.status() is ChannelStatus.ERROR


def test_a_paired_ready_device_connects():
    sim = channel(FakeAdb())
    sim.connect()
    assert sim.status() is ChannelStatus.CONNECTED
    assert sim.list_channels() == [AGENT]
    sim.disconnect()
    assert sim.status() is ChannelStatus.DISCONNECTED


# --- sending -----------------------------------------------------------

def test_delivery_is_claimed_only_after_the_sent_box_shows_it():
    adb = FakeAdb(sent=[{"_id": "9", "address": OWNER, "body": "Approve $650 charter?"}])
    sim = channel(adb)
    sim.connect()
    assert sim.send(OWNER, "Approve $650 charter?") is True


def test_a_command_that_returned_zero_is_not_delivery():
    """The sent box is empty, so the outcome is uncertain, not success."""
    adb = FakeAdb(sent=[])
    sim = channel(adb)
    sim.connect()
    assert sim.send(OWNER, "Approve $650 charter?") is False


def test_a_failed_send_command_is_a_failure():
    sim = channel(FakeAdb(fail=("send",)))
    sim.connect()
    assert sim.send(OWNER, "anything") is False


def test_it_refuses_a_non_e164_recipient():
    sim = channel(FakeAdb())
    sim.connect()
    assert sim.send("5550000001", "hello") is False
    assert sim.send("", "hello") is False


def test_it_refuses_an_empty_message():
    sim = channel(FakeAdb())
    sim.connect()
    assert sim.send(OWNER, "   ") is False


def test_it_will_not_send_before_connecting():
    sim = channel(FakeAdb())
    assert sim.send(OWNER, "hello") is False


# --- receiving ---------------------------------------------------------

def test_inbound_messages_carry_their_device_evidence():
    adb = FakeAdb(inbox=[{"_id": "11", "address": OWNER, "body": "YES 4ccad013", "date": "1774000000000"}])
    sim = channel(adb)
    sim._high_water = 10
    sim._status = ChannelStatus.CONNECTED
    received = sim.poll_once()
    assert len(received) == 1
    assert received[0].content == "YES 4ccad013"
    assert received[0].sender == OWNER
    assert received[0].metadata["transport"] == "real_sim"
    assert received[0].metadata["evidence"] == "content://sms/inbox/11"
    assert received[0].message_id == f"{SERIAL}:11"


def test_an_overlapping_poll_cannot_replay_an_approval():
    """The provider row id is the dedupe key, so a YES is delivered once."""
    adb = FakeAdb(inbox=[{"_id": "11", "address": OWNER, "body": "YES 4ccad013"}])
    sim = channel(adb)
    sim._high_water = 10
    sim._status = ChannelStatus.CONNECTED
    assert len(sim.poll_once()) == 1
    assert sim.poll_once() == []


def test_the_high_water_mark_advances():
    adb = FakeAdb(inbox=[{"_id": "11", "address": OWNER, "body": "one"},
                         {"_id": "12", "address": OWNER, "body": "two"}])
    sim = channel(adb)
    sim._high_water = 10
    sim._status = ChannelStatus.CONNECTED
    sim.poll_once()
    assert sim._high_water == 12


def test_an_unreadable_inbox_yields_nothing_rather_than_guessing():
    sim = channel(FakeAdb(fail=("inbox",)))
    sim._status = ChannelStatus.CONNECTED
    assert sim.poll_once() == []


def test_handlers_receive_inbound_messages():
    adb = FakeAdb(inbox=[{"_id": "11", "address": OWNER, "body": "YES"}])
    sim = channel(adb)
    sim._high_water = 10
    sim._status = ChannelStatus.CONNECTED
    seen = []
    sim.on_message(seen.append)
    for message in sim.poll_once():
        sim._dispatch(message)
    assert [m.content for m in seen] == ["YES"]


def test_one_raising_handler_does_not_stop_the_others():
    adb = FakeAdb(inbox=[{"_id": "11", "address": OWNER, "body": "YES"}])
    sim = channel(adb)
    sim._high_water = 10
    sim._status = ChannelStatus.CONNECTED
    seen = []

    def broken(_message):
        raise RuntimeError("test-only")

    sim.on_message(broken)
    sim.on_message(seen.append)
    for message in sim.poll_once():
        sim._dispatch(message)
    assert len(seen) == 1


# --- health ------------------------------------------------------------

def test_health_reports_what_is_actually_true():
    sim = channel(FakeAdb())
    sim.connect()
    health = sim.health()
    assert health["serial"] == SERIAL
    assert health["number"] == AGENT
    assert health["attached"] is True
    assert health["sim_ready"] is True
    assert health["status"] == "connected"


def test_health_reports_a_detached_phone():
    adb = FakeAdb()
    sim = channel(adb)
    sim.connect()
    adb.attached = []
    adb.sim = "ABSENT"
    health = sim.health()
    assert health["attached"] is False
    assert health["sim_ready"] is False


# --- registration ------------------------------------------------------

def test_the_channel_is_discoverable_in_the_registry():
    from openjarvis.core.registry import ChannelRegistry
    import openjarvis.channels  # noqa: F401  triggers registration

    names = ChannelRegistry.list() if hasattr(ChannelRegistry, "list") else None
    if names is None:
        pytest.skip("registry does not expose a listing in this version")
    assert "android_sim" in names


def test_no_cloud_provider_appears_in_this_adapter():
    """The whole point: nobody else is in the path."""
    import pathlib

    import openjarvis.channels.android_sim as module

    source = pathlib.Path(module.__file__).read_text().lower()
    for vendor in ("twilio", "sendblue", "messagebird", "vonage", "plivo", "bandwidth"):
        # A comment naming what this replaces is fine; an import or a call is not.
        assert f"import {vendor}" not in source
        assert f"{vendor}.com" not in source
