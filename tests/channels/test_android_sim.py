"""The real-SIM channel: SMS through the box's own phone, by its screen.

MOCK-BASED. The phone is the simulator in tests/phone/fake_phone.py. These
tests cover the channel's contract — device binding, the App Map gate, and
what it will and will not claim about a message — and satisfy no
physical-device acceptance gate.
"""

from __future__ import annotations

import pytest

from openjarvis.channels._stubs import ChannelStatus
from openjarvis.channels.android_sim import (
    DEFAULT_APP_MAP,
    AndroidSimChannel,
    resolve_app_map,
)
from openjarvis.core.registry import ChannelRegistry
from openjarvis.phone.appmap import UnvalidatedAppMap, builtin_map_path, load_app_map
from openjarvis.phone.device import PhoneDevice, is_screen_verb
from openjarvis.phone.messages import MessagesProcedure
from tests.phone.fake_phone import FakePhone

NUMBER = "+12515551234"
OWN = "+12515550100"
BODY = "Approve the 40 ft charter Saturday 7am, $850? Reply YES"


@pytest.fixture
def phone() -> FakePhone:
    return FakePhone()


@pytest.fixture
def app_map():
    return load_app_map(builtin_map_path(DEFAULT_APP_MAP), calibrating=True)


@pytest.fixture
def channel(phone, app_map):
    device = PhoneDevice(phone.serial, phone, settle=0.0)
    procedure = MessagesProcedure(device, app_map, step_pause=0.0, observe_pause=0.0)
    made = AndroidSimChannel(
        serial=phone.serial,
        own_number=OWN,
        app_map=app_map,
        device=device,
        procedure=procedure,
        poll_seconds=3600,
    )
    yield made
    made.disconnect()


# --- registration --------------------------------------------------------


def test_the_channel_registers_under_its_own_id():
    # Registries are cleared between tests, so re-register the way the
    # decorator does at import time and check the key it claims.
    if not ChannelRegistry.contains("android_sim"):
        ChannelRegistry.register_value("android_sim", AndroidSimChannel)
    assert ChannelRegistry.get("android_sim") is AndroidSimChannel
    assert AndroidSimChannel.channel_id == "android_sim"


# --- binding to one device ----------------------------------------------


def test_it_connects_to_the_configured_phone(channel):
    channel.connect()
    assert channel.status() is ChannelStatus.CONNECTED
    assert channel.list_channels() == [OWN]


def test_it_refuses_a_different_phone_even_if_it_is_the_only_one_attached(
    phone, app_map
):
    device = PhoneDevice("EXPECTED_SERIAL", phone, settle=0.0)
    made = AndroidSimChannel(
        serial="EXPECTED_SERIAL",
        own_number=OWN,
        app_map=app_map,
        device=device,
        poll_seconds=3600,
    )
    made.connect()
    assert made.status() is ChannelStatus.ERROR


def test_it_refuses_without_a_serial(app_map, monkeypatch):
    monkeypatch.delenv("NG_ANDROID_SERIAL", raising=False)
    made = AndroidSimChannel(own_number=OWN, app_map=app_map)
    made.connect()
    assert made.status() is ChannelStatus.ERROR


@pytest.mark.parametrize("number", ["", "2515550100", "+1 251 555 0100", "abc"])
def test_it_refuses_a_number_that_is_not_e164(phone, app_map, number):
    device = PhoneDevice(phone.serial, phone, settle=0.0)
    made = AndroidSimChannel(
        serial=phone.serial, own_number=number, app_map=app_map, device=device
    )
    made.connect()
    assert made.status() is ChannelStatus.ERROR


def test_it_refuses_a_phone_with_no_ready_sim(phone, app_map):
    phone.sim = "ABSENT"
    device = PhoneDevice(phone.serial, phone, settle=0.0)
    made = AndroidSimChannel(
        serial=phone.serial, own_number=OWN, app_map=app_map, device=device
    )
    made.connect()
    assert made.status() is ChannelStatus.ERROR


def test_it_refuses_when_adb_is_not_installed(phone, app_map):
    phone.adb_present = False
    device = PhoneDevice(phone.serial, phone, settle=0.0)
    made = AndroidSimChannel(
        serial=phone.serial, own_number=OWN, app_map=app_map, device=device
    )
    made.connect()
    assert made.status() is ChannelStatus.ERROR


# --- the App Map gate ----------------------------------------------------


def test_an_unvalidated_app_map_stops_the_channel_connecting(phone, monkeypatch):
    monkeypatch.delenv("NG_APPMAP_CALIBRATING", raising=False)
    device = PhoneDevice(phone.serial, phone, settle=0.0)
    made = AndroidSimChannel(
        serial=phone.serial, own_number=OWN, device=device, calibrating=False
    )
    made.connect()
    assert made.status() is ChannelStatus.ERROR
    report = made.health()
    assert report["app_map_validated"] is False
    # The reason is reported, not swallowed: an operator needs to know the
    # map has not been confirmed against this phone.
    assert "validated" in report["app_map_error"]


def test_the_shipped_map_loads_only_while_calibrating():
    with pytest.raises(UnvalidatedAppMap):
        resolve_app_map(DEFAULT_APP_MAP)
    assert resolve_app_map(DEFAULT_APP_MAP, calibrating=True).id == DEFAULT_APP_MAP


def test_a_map_can_be_given_by_path(tmp_path):
    from openjarvis.phone.appmap import REQUIRED_ELEMENTS

    body = "\n".join(
        [
            "[app_map]",
            'id = "demo"',
            'package = "com.example.messages"',
            'launch_activity = "com.example.messages.Main"',
            "validated = true",
            'validated_on = "com.example.messages 1.0 on a bench device"',
            "[app_map.elements]",
            *[f'{name} = {{ resource_id = "{name}" }}' for name in REQUIRED_ELEMENTS],
        ]
    )
    path = tmp_path / "demo.toml"
    path.write_text(body, encoding="utf-8")
    assert resolve_app_map(str(path)).package == "com.example.messages"


# --- sending -------------------------------------------------------------


def test_a_send_goes_through_the_screen_and_only_screen_verbs_are_issued(
    channel, phone
):
    channel.connect()
    assert channel.send(NUMBER, BODY) is True
    assert phone.threads[NUMBER].bubbles[-1].body == BODY
    assert phone.refused == []
    assert all(is_screen_verb(command) for command in phone.commands)


def test_it_will_not_send_before_it_is_connected(channel, phone):
    assert channel.send(NUMBER, BODY) is False
    assert phone.commands == []


def test_a_failure_marker_on_screen_is_reported_as_a_failure(channel, phone):
    channel.connect()
    phone.send_fails = True
    assert channel.send(NUMBER, BODY) is False


def test_an_uncertain_outcome_is_not_reported_as_success(channel, phone, monkeypatch):
    channel.connect()
    monkeypatch.setattr(phone, "_send", lambda: None)
    assert channel.send(NUMBER, BODY) is False


def test_the_bus_is_told_what_the_screen_showed(channel, phone):
    published = []

    class Recorder:
        def publish(self, event_type, payload):
            published.append((event_type, payload))

    channel._bus = Recorder()
    channel.connect()
    channel.send(NUMBER, BODY)
    assert published
    _, payload = published[-1]
    assert payload["delivery"] == "sent"
    assert payload["transport"] == "screen"
    assert payload["evidence"]


def test_an_uncertain_send_says_uncertain_on_the_bus(channel, phone, monkeypatch):
    published = []

    class Recorder:
        def publish(self, event_type, payload):
            published.append(payload)

    channel._bus = Recorder()
    channel.connect()
    monkeypatch.setattr(phone, "_send", lambda: None)
    channel.send(NUMBER, BODY)
    assert published[-1]["delivery"] == "uncertain"


# --- receiving -----------------------------------------------------------


def test_connecting_baselines_the_inbox_so_history_is_not_replayed(channel, phone):
    phone.receive(NUMBER, "a message from before the box came up")
    channel.connect()
    assert channel.poll_once() == []


def test_a_reply_is_delivered_once_with_its_provenance(channel, phone):
    channel.connect()
    channel.send(NUMBER, BODY)
    phone.receive(NUMBER, "YES")

    received = channel.poll_once()
    assert len(received) == 1
    message = received[0]
    assert message.content == "YES"
    assert message.sender == NUMBER
    assert message.channel == "android_sim"
    assert message.metadata["transport"] == "screen"
    assert message.metadata["received_on"] == OWN
    assert "screen" in message.metadata["evidence"]
    assert message.message_id.startswith(phone.serial + ":")

    assert channel.poll_once() == []


def test_the_message_id_is_stable_for_the_same_bubble(channel, phone):
    channel.connect()
    phone.receive(NUMBER, "YES")
    first = channel.poll_once()[0]
    assert first.message_id == f"{phone.serial}:{first.metadata['fingerprint']}"


def test_handlers_see_inbound_messages(channel, phone):
    seen = []
    channel.on_message(seen.append)
    channel.connect()
    phone.receive(NUMBER, "YES")
    for message in channel.poll_once():
        channel._dispatch(message)
    assert [message.content for message in seen] == ["YES"]


def test_a_raising_handler_does_not_stop_the_others(channel, phone):
    seen = []

    def explode(message):
        raise RuntimeError("handler bug")

    channel.on_message(explode)
    channel.on_message(seen.append)
    channel.connect()
    phone.receive(NUMBER, "YES")
    for message in channel.poll_once():
        channel._dispatch(message)
    assert len(seen) == 1


def test_polling_before_connecting_yields_nothing(channel):
    assert channel.poll_once() == []


# --- health --------------------------------------------------------------


def test_health_answers_before_the_channel_connects(phone):
    # The owner's device page asks this first, and the answer it needs is
    # whether the map has been confirmed against a phone.
    probe = AndroidSimChannel(serial=phone.serial, own_number=OWN)
    report = probe.health()
    assert report["app_map"] == DEFAULT_APP_MAP
    assert report["app_map_validated"] is False
    assert report["app_map_confirmed_against"] == ""
    assert report["attached"] is False
    assert report["transport"] == "screen"


def test_health_reports_what_it_knows_and_says_screen(channel, phone):
    channel.connect()
    report = channel.health()
    assert report["serial"] == phone.serial
    assert report["number"] == OWN
    assert report["attached"] is True
    assert report["sim_ready"] is True
    assert report["transport"] == "screen"
    assert report["app_map"] == DEFAULT_APP_MAP
    assert report["status"] == ChannelStatus.CONNECTED.value


def test_health_reports_a_detached_phone_rather_than_guessing(channel, phone):
    channel.connect()
    phone.attached = False
    report = channel.health()
    assert report["attached"] is False
    assert report["sim_ready"] is False


def test_disconnect_stops_the_watcher(channel):
    channel.connect()
    channel.disconnect()
    assert channel.status() is ChannelStatus.DISCONNECTED


# --- no provider, no send api, no message database -----------------------


def test_no_cloud_provider_appears_in_this_adapter():
    import pathlib

    import openjarvis.channels.android_sim as module

    source = pathlib.Path(module.__file__).read_text(encoding="utf-8").lower()
    for vendor in (
        "twilio",
        "sendblue",
        "messagebird",
        "vonage",
        "plivo",
        "bandwidth",
        "telnyx",
        "sinch",
    ):
        assert f"import {vendor}" not in source
        assert f"{vendor}.com" not in source


def test_the_adapter_makes_no_network_call_of_its_own():
    import ast
    import pathlib

    import openjarvis.channels.android_sim as module

    tree = ast.parse(pathlib.Path(module.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    # No HTTP client and no socket: the only thing this channel talks to is
    # the phone in front of it, through the screen driver.
    assert not imported & {
        "urllib",
        "http",
        "requests",
        "httpx",
        "socket",
        "websockets",
    }


def test_the_adapter_issues_no_shell_command_itself():
    import ast
    import pathlib

    import openjarvis.channels.android_sim as module

    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    called = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            target = node.func
            name = getattr(target, "attr", None) or getattr(target, "id", None)
            if name:
                called.add(name)
    assert "run" not in called
    assert "Popen" not in called
    # It asks the driver to do things; it never builds a device command.
    assert "shell" not in called
