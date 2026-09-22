"""The phone's app list. MOCK-BASED; see fake_phone.py."""

from __future__ import annotations

import pytest

from openjarvis.phone.apps import (
    DERIVED,
    HINTED,
    InstalledApp,
    derive_label,
    launchable,
    list_installed,
    load_label_hints,
    parse_component,
    parse_packages,
)
from openjarvis.phone.device import ForbiddenDeviceCommand, is_screen_verb

# --- only the read forms of pm are reachable ----------------------------

WRITE_FORMS = [
    "pm install /data/local/tmp/x.apk",
    "pm uninstall com.example",
    "pm grant com.example android.permission.SEND_SMS",
    "pm revoke com.example android.permission.SEND_SMS",
    "pm disable com.example",
    "pm clear com.example",
    "pm list packages",  # every package, including system; not what a launcher asks
    "pm list packages -3 ; su",
]


@pytest.mark.parametrize("command", WRITE_FORMS)
def test_only_the_exact_read_forms_are_allowed(command):
    assert not is_screen_verb(command)


def test_the_two_inventory_reads_are_allowed():
    assert is_screen_verb("pm list packages -3")
    assert is_screen_verb(
        "cmd package resolve-activity --brief"
        " -c android.intent.category.LAUNCHER com.facebook.katana"
    )


def test_listing_apps_issues_nothing_but_allowed_commands(device, phone):
    phone.installed = {"com.instagram.android": "com.instagram.MainTabActivity"}
    list_installed(device, hints={})
    assert phone.refused == []
    assert all(is_screen_verb(command) for command in phone.commands)


def test_a_write_form_would_be_refused_by_the_driver(device):
    with pytest.raises(ForbiddenDeviceCommand):
        device.shell.shell("pm uninstall com.example")


# --- parsing ------------------------------------------------------------


def test_packages_are_parsed_deduped_and_sorted():
    assert parse_packages("package:com.b\npackage:com.a\nnoise\npackage:com.a\n") == [
        "com.a",
        "com.b",
    ]


def test_noise_around_the_package_lines_is_ignored():
    assert parse_packages("") == []
    assert parse_packages("error: device offline") == []


def test_the_component_is_found_past_a_priority_line():
    assert (
        parse_component("priority=0 preferredOrder=0 match=0x0\ncom.x/com.x.Main\n")
        == "com.x/com.x.Main"
    )


def test_no_component_means_empty_not_a_wrong_guess():
    assert parse_component("No activity found\n") == ""
    assert parse_component("") == ""


# --- names --------------------------------------------------------------


def test_a_derived_name_drops_a_meaningless_trailing_segment():
    assert derive_label("com.instagram.android") == "Instagram"
    assert derive_label("com.spotify.music") == "Music"
    assert derive_label("com.facebook.katana") == "Katana"


def test_a_derived_name_splits_camel_case_and_underscores():
    assert derive_label("com.example.myGreatApp") == "My Great App"
    assert derive_label("com.example.my_tool") == "My Tool"


def test_a_package_with_nothing_to_go_on_is_returned_as_is():
    assert derive_label("") == ""
    assert derive_label("singleword") == "Singleword"


def test_the_shipped_hints_name_the_apps_a_derivation_gets_wrong():
    hints = load_label_hints()
    assert hints["com.facebook.katana"] == "Facebook"
    assert hints["com.toasttab.toastpos"] == "Toast POS"
    # These are the ones a derived name gets plainly wrong.
    assert derive_label("com.facebook.katana") != hints["com.facebook.katana"]


def test_missing_or_broken_hints_are_no_hints_rather_than_an_error(tmp_path):
    assert load_label_hints(tmp_path / "absent.toml") == {}
    broken = tmp_path / "broken.toml"
    broken.write_text("[labels]\nthis is not toml", encoding="utf-8")
    assert load_label_hints(broken) == {}
    wrong_shape = tmp_path / "wrong.toml"
    wrong_shape.write_text('labels = "nope"\n', encoding="utf-8")
    assert load_label_hints(wrong_shape) == {}


# --- the listing --------------------------------------------------------


def test_apps_come_back_with_their_launch_activity(device, phone):
    phone.installed = {
        "com.facebook.katana": "com.facebook.katana.LoginActivity",
        "com.instagram.android": "com.instagram.MainTabActivity",
    }
    apps = list_installed(device, hints={"com.facebook.katana": "Facebook"})
    by_package = {app.package: app for app in apps}
    assert by_package["com.facebook.katana"].label == "Facebook"
    assert by_package["com.facebook.katana"].label_source == HINTED
    assert by_package["com.facebook.katana"].name_is_derived is False
    assert by_package["com.instagram.android"].label == "Instagram"
    assert by_package["com.instagram.android"].label_source == DERIVED
    assert by_package["com.instagram.android"].name_is_derived is True
    assert (
        by_package["com.instagram.android"].activity == "com.instagram.MainTabActivity"
    )


def test_an_app_with_no_launcher_activity_is_listed_but_not_launchable(device, phone):
    phone.installed = {
        "com.example.service": "",
        "com.example.real": "com.example.Main",
    }
    apps = list_installed(device, hints={})
    assert {app.package: app.launchable for app in apps} == {
        "com.example.service": False,
        "com.example.real": True,
    }
    assert [app.package for app in launchable(apps)] == ["com.example.real"]


def test_launchable_apps_come_back_in_name_order(device, phone):
    phone.installed = {
        "com.b.zebra": "com.b.Main",
        "com.a.apple": "com.a.Main",
        "com.c.Mango": "com.c.Main",
    }
    apps = launchable(list_installed(device, hints={}))
    assert [app.label for app in apps] == ["Apple", "Mango", "Zebra"]


def test_a_detached_phone_yields_no_apps_rather_than_a_stale_list(device, phone):
    phone.installed = {"com.example.real": "com.example.Main"}
    phone.attached = False
    assert list_installed(device, hints={}) == []
    assert phone.commands == []


def test_a_phone_that_will_not_answer_yields_nothing(device, phone, monkeypatch):
    from openjarvis.phone.device import ShellResult

    original = phone.shell

    def fail_listing(command: str, timeout: int = 20):
        if command == "pm list packages -3":
            return ShellResult(1, "", "error: closed")
        return original(command, timeout)

    monkeypatch.setattr(phone, "shell", fail_listing)
    assert list_installed(device, hints={}) == []


def test_the_listing_is_capped_so_one_call_cannot_stall_the_screen(device, phone):
    phone.installed = {
        f"com.example.app{index:03d}": "com.example.Main" for index in range(50)
    }
    apps = list_installed(device, hints={}, limit=10)
    assert len(apps) == 10


def test_nothing_installed_is_an_empty_list_not_an_error(device, phone):
    assert list_installed(device, hints={}) == []


def test_an_installed_app_knows_whether_its_name_was_guessed():
    guessed = InstalledApp("com.x.katana", "com.x.Main", "Katana", DERIVED)
    known = InstalledApp("com.x.katana", "com.x.Main", "Facebook", HINTED)
    assert guessed.name_is_derived is True
    assert known.name_is_derived is False
