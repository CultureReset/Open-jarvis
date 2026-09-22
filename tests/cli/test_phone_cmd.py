"""``jarvis phone`` — MOCK-BASED. The phone is the simulator, not hardware."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from openjarvis.cli import phone_cmd
from openjarvis.phone.device import PhoneDevice
from tests.phone.fake_phone import FakePhone


@pytest.fixture(autouse=True)
def wide_terminal(monkeypatch):
    # rich truncates table cells to the terminal width, which would make
    # these assertions about width rather than about behaviour.
    monkeypatch.setenv("COLUMNS", "220")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def attached(monkeypatch) -> FakePhone:
    fake = FakePhone()
    monkeypatch.setenv("NG_ANDROID_SERIAL", fake.serial)
    monkeypatch.setattr(
        phone_cmd, "_device", lambda serial: PhoneDevice(serial, fake, settle=0.0)
    )
    return fake


def test_maps_lists_the_shipped_map_and_says_it_is_not_validated(runner):
    result = runner.invoke(phone_cmd.phone, ["maps"])
    assert result.exit_code == 0
    assert "google_messages" in result.output
    assert "com.google.android.apps.messaging" in result.output
    assert "validated = true" in result.output


def test_a_command_without_a_serial_says_which_phone_it_needs(runner, monkeypatch):
    monkeypatch.delenv("NG_ANDROID_SERIAL", raising=False)
    for command in ("screen", "calibrate"):
        result = runner.invoke(phone_cmd.phone, [command])
        assert result.exit_code != 0
        assert "NG_ANDROID_SERIAL" in result.output


def test_screen_prints_the_identifiers_a_selector_would_use(runner, attached):
    attached.receive("+12515551234", "Any openings Saturday?")
    result = runner.invoke(phone_cmd.phone, ["screen"])
    assert result.exit_code == 0
    assert "conversation_name" in result.output
    assert "start_new_conversation_button" in result.output
    assert "node(s) with something readable" in result.output


def test_calibrating_one_screen_reports_found_elements(runner, attached):
    attached.receive("+12515551234", "Any openings Saturday?")
    result = runner.invoke(
        phone_cmd.phone, ["calibrate", "--map", "google_messages", "--screen", "list"]
    )
    assert result.exit_code == 0
    assert "conversation_list_anchor" in result.output
    assert "missing" not in result.output
    # It reports success but will not mark the map validated itself: that is
    # a claim about hardware only a person who watched it can make.
    assert "validated = true" in result.output
    assert "seen working on this hardware" in result.output


def test_calibration_on_an_empty_inbox_reports_the_row_it_could_not_see(
    runner, attached
):
    # With no conversations there is no row to find, and the report says so
    # rather than passing a screen it could not actually check.
    result = runner.invoke(
        phone_cmd.phone, ["calibrate", "--map", "google_messages", "--screen", "list"]
    )
    assert result.exit_code == 1
    assert "missing conversation_row" in result.output


def test_calibration_names_the_elements_it_could_not_find(runner, attached, tmp_path):
    from openjarvis.phone.appmap import REQUIRED_ELEMENTS

    body = "\n".join(
        [
            "[app_map]",
            'id = "wrong"',
            'package = "com.google.android.apps.messaging"',
            'launch_activity = "com.google.android.apps.messaging.ui.'
            'ConversationListActivity"',
            "validated = false",
            "[app_map.elements]",
            *[
                f'{name} = {{ resource_id = "definitely_not_{name}" }}'
                for name in REQUIRED_ELEMENTS
            ],
        ]
    )
    path = tmp_path / "wrong.toml"
    path.write_text(body, encoding="utf-8")

    result = runner.invoke(
        phone_cmd.phone, ["calibrate", "--map", str(path), "--screen", "list"]
    )
    assert result.exit_code == 1
    assert "missing" in result.output
    assert "conversation_list_anchor" in result.output
    assert "were not found" in result.output


def test_an_unknown_screen_name_is_rejected(runner, attached):
    result = runner.invoke(phone_cmd.phone, ["calibrate", "--screen", "inbox"])
    assert result.exit_code != 0
    assert "must be one of" in result.output


def test_a_map_that_does_not_exist_is_reported_not_crashed(runner, attached):
    result = runner.invoke(phone_cmd.phone, ["calibrate", "--map", "no_such_map"])
    assert result.exit_code != 0
    assert "No App Map" in result.output
