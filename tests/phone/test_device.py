"""The driver may tap, type, press and look. Nothing else.

These are boundary tests, and they are the reason the module exists. The
point of driving the phone by its screen is lost the moment one shortcut
sneaks back in, so the allowlist is tested directly rather than trusted to
review.
"""

from __future__ import annotations

import pytest

from openjarvis.phone.device import (
    DUMP_PATH,
    ForbiddenDeviceCommand,
    PhoneDevice,
    ScreenOnlyShell,
    encode_typing,
    is_screen_verb,
)

# Each of these would get a message sent or read without the screen being
# involved, which is exactly what this driver exists to prevent.
BACKDOORS = [
    "service call isms 5 i32 1 s16 'null' s16 '+12515551234' s16 'null' s16 'hi'",
    "service call isms 7 i32 1",
    "content query --uri content://sms/inbox --projection _id:address:body",
    "content query --uri content://sms/sent",
    "content insert --uri content://sms/sent --bind address:s:+1",
    "am start -a android.intent.action.SENDTO -d sms:+12515551234",
    "am start -a android.intent.action.VIEW -d smsto:+12515551234 --es sms_body hi",
    "am broadcast -a android.provider.Telephony.SMS_DELIVER",
    "sqlite3 /data/data/com.android.providers.telephony/databases/mmssms.db"
    " 'select * from sms'",
    "pm grant com.example android.permission.SEND_SMS",
    "settings put global airplane_mode_on 1",
    "su -c 'id'",
    "svc data disable",
    "curl https://api.twilio.com/2010-04-01/Messages.json",
]

SCREEN_VERBS = [
    "input tap 540 1200",
    "input swipe 540 700 540 1800",
    "input swipe 540 700 540 1800 400",
    "input keyevent KEYCODE_HOME",
    "input keyevent KEYCODE_APOSTROPHE",
    "input text 'Reply%sYES'",
    f"uiautomator dump {DUMP_PATH}",
    f"cat {DUMP_PATH}",
    f"rm -f {DUMP_PATH}",
    "am start -W -a android.intent.action.MAIN -c android.intent.category.LAUNCHER"
    " -n com.google.android.apps.messaging/com.google.android.apps.messaging.ui."
    "ConversationListActivity",
    "am force-stop com.google.android.apps.messaging",
    "getprop gsm.sim.state",
    "dumpsys package com.google.android.apps.messaging",
    "wm size",
    "echo ok",
]


@pytest.mark.parametrize("command", BACKDOORS)
def test_backdoor_commands_are_not_screen_verbs(command):
    assert not is_screen_verb(command)


@pytest.mark.parametrize("command", SCREEN_VERBS)
def test_screen_verbs_are_allowed(command):
    assert is_screen_verb(command)


@pytest.mark.parametrize("command", BACKDOORS)
def test_shell_refuses_backdoors_loudly(command):
    shell = ScreenOnlyShell("SERIAL1", adb="/nonexistent/adb")
    with pytest.raises(ForbiddenDeviceCommand) as raised:
        shell.shell(command)
    # The refusal names the command, so a refusal is auditable rather than a
    # silent no-op somebody debugs for an hour.
    assert command[:20] in str(raised.value)


def test_a_screen_verb_with_a_backdoor_appended_is_refused():
    shell = ScreenOnlyShell("SERIAL1", adb="/nonexistent/adb")
    with pytest.raises(ForbiddenDeviceCommand):
        shell.shell("input tap 10 20; service call isms 5")
    with pytest.raises(ForbiddenDeviceCommand):
        shell.shell("input tap 10 20 && content query --uri content://sms/inbox")


def test_patterns_are_anchored_so_a_prefix_does_not_admit_arguments():
    assert not is_screen_verb("input tap 10 20 extra")
    assert not is_screen_verb("wm size && su")
    assert not is_screen_verb("getprop ro.serialno")
    assert not is_screen_verb(f"cat {DUMP_PATH} /etc/hosts")
    assert not is_screen_verb("uiautomator dump /sdcard/elsewhere.xml")


def test_launching_an_app_is_limited_to_a_main_launcher_activity():
    assert not is_screen_verb(
        "am start -W -a android.intent.action.MAIN -c android.intent.category.LAUNCHER"
        " -n com.example/.Main --es sms_body hi"
    )
    assert not is_screen_verb("am start -n com.example/.Main -d sms:+1")


def test_a_driver_must_be_bound_to_a_serial():
    with pytest.raises(ValueError):
        ScreenOnlyShell("")


def test_typing_encodes_spaces_and_presses_the_quote_key():
    # input text reads %s as a space and has no escape for a single quote.
    assert encode_typing("Reply YES") == ["input text 'Reply%sYES'"]
    assert encode_typing("it's on") == [
        "input text 'it'",
        "input keyevent KEYCODE_APOSTROPHE",
        "input text 's%son'",
    ]
    assert all(is_screen_verb(command) for command in encode_typing("a 'b' c"))


def test_typing_a_long_body_is_chunked_and_every_chunk_is_a_screen_verb():
    commands = encode_typing("x" * 500)
    assert len(commands) > 1
    assert all(is_screen_verb(command) for command in commands)
    assert (
        "".join(command[len("input text '") : -1] for command in commands) == "x" * 500
    )


def test_typing_nothing_issues_nothing():
    assert encode_typing("") == []


def test_tap_refuses_negative_coordinates(device, phone):
    assert device.tap(-1, 10) is False
    assert not any(command.startswith("input tap") for command in phone.commands)


def test_tap_node_refuses_a_node_with_no_area(device, phone):
    from openjarvis.phone.uitree import Bounds, UiNode

    invisible = UiNode(text="Send", bounds=Bounds(0, 0, 0, 0), clickable=True)
    assert device.tap_node(invisible) is False
    assert not any(command.startswith("input tap") for command in phone.commands)


def test_tap_node_taps_the_row_when_the_label_itself_is_not_clickable(device, phone):
    from openjarvis.phone.uitree import Selector, find

    phone.receive("+12515551234", "hello")
    row = find(device.screen(), Selector(resource_id="conversation_name"))
    assert row is not None and row.clickable is False
    host = row.nearest_clickable()
    assert host is not row and host.clickable is True
    assert device.tap_node(row) is True
    assert f"input tap {host.center[0]} {host.center[1]}" in phone.commands


def test_reading_the_screen_cleans_up_after_itself(device, phone):
    assert device.screen() is not None
    assert f"rm -f {DUMP_PATH}" in phone.commands


def test_every_command_the_driver_issues_is_a_screen_verb(device, phone):
    device.wake()
    device.home()
    device.screen()
    device.tap(100, 100)
    device.swipe(100, 800, 100, 300)
    device.type_text("hello 'there'")
    device.open_app("com.google.android.apps.messaging", "com.example.Activity")
    device.screen_size()
    device.sim_ready()
    device.package_version("com.google.android.apps.messaging")
    assert phone.commands
    assert phone.refused == []
    assert all(is_screen_verb(command) for command in phone.commands)


def test_clear_field_presses_delete_a_bounded_number_of_times(device, phone):
    device.clear_focused_field(length=6, headroom=2)
    deletes = [c for c in phone.commands if c == "input keyevent KEYCODE_DEL"]
    assert len(deletes) == 8


def test_device_reports_absence_rather_than_guessing(phone):
    phone.attached = False
    driver = PhoneDevice(phone.serial, phone, settle=0.0)
    assert driver.attached() is False
