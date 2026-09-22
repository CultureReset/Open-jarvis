"""App Maps are data, and a map nobody has confirmed must not drive a phone."""

from __future__ import annotations

import pytest

from openjarvis.phone.appmap import (
    REQUIRED_ELEMENTS,
    AppMapError,
    UnvalidatedAppMap,
    builtin_map_path,
    list_app_maps,
    load_app_map,
    missing_on_screen,
    parse_app_map,
)
from openjarvis.phone.uitree import Bounds, UiNode, parse_ui_dump

MINIMAL = {
    "app_map": {
        "id": "demo",
        "package": "com.example.messages",
        "launch_activity": "com.example.messages.Main",
        "validated": True,
        "elements": {name: {"resource_id": name} for name in REQUIRED_ELEMENTS},
    }
}


def _minimal(**overrides):
    import copy

    data = copy.deepcopy(MINIMAL)
    data["app_map"].update(overrides)
    return data


def test_a_map_parses_into_named_selector_lists():
    app_map = parse_app_map(MINIMAL)
    assert app_map.package == "com.example.messages"
    assert [selector.resource_id for selector in app_map.selectors("send_button")] == [
        "send_button"
    ]


def test_a_missing_required_element_is_rejected_at_load_not_mid_send():
    data = _minimal()
    del data["app_map"]["elements"]["send_button"]
    with pytest.raises(AppMapError) as raised:
        parse_app_map(data)
    assert "send_button" in str(raised.value)


def test_an_unknown_element_name_is_rejected_so_a_typo_is_not_silently_dead():
    data = _minimal()
    data["app_map"]["elements"]["send_buton"] = {"resource_id": "x"}
    with pytest.raises(AppMapError) as raised:
        parse_app_map(data)
    assert "send_buton" in str(raised.value)


def test_a_map_without_a_package_or_activity_cannot_open_anything():
    for field in ("package", "launch_activity"):
        data = _minimal()
        data["app_map"][field] = ""
        with pytest.raises(AppMapError):
            parse_app_map(data)


def test_an_empty_selector_is_rejected_because_it_matches_the_whole_screen():
    data = _minimal()
    data["app_map"]["elements"]["send_button"] = {}
    with pytest.raises(AppMapError) as raised:
        parse_app_map(data)
    assert "empty selector" in str(raised.value)


def test_an_unknown_selector_field_names_itself_in_the_error():
    data = _minimal()
    data["app_map"]["elements"]["send_button"] = {"resourceId": "x"}
    with pytest.raises(AppMapError) as raised:
        parse_app_map(data)
    assert "resourceId" in str(raised.value)


def test_a_list_of_selectors_is_an_ordered_set_of_fallbacks():
    data = _minimal()
    data["app_map"]["elements"]["send_button"] = [
        {"resource_id": "send_message_button_icon"},
        {"content_desc_contains": "send"},
    ]
    app_map = parse_app_map(data)
    assert len(app_map.selectors("send_button")) == 2


def test_a_file_with_no_app_map_table_is_rejected():
    with pytest.raises(AppMapError):
        parse_app_map({"operator": {}})


def test_side_strategy_selector_needs_selectors_to_tell_the_sides_apart():
    data = _minimal(side_strategy="selector")
    with pytest.raises(AppMapError):
        parse_app_map(data)


def test_an_unknown_side_strategy_is_rejected():
    with pytest.raises(AppMapError):
        parse_app_map(_minimal(side_strategy="vibes"))


def test_outgoing_left_fraction_must_be_a_fraction():
    for bad in (0, 1, 1.5, -0.2, "wide"):
        with pytest.raises(AppMapError):
            parse_app_map(_minimal(outgoing_left_fraction=bad))


def test_alignment_tells_the_two_sides_of_a_thread_apart():
    app_map = parse_app_map(MINIMAL)
    incoming = UiNode(text="YES", bounds=Bounds(40, 300, 520, 380))
    outgoing = UiNode(text="Approve?", bounds=Bounds(560, 300, 1040, 380))
    assert app_map.is_outgoing(incoming, 1080) is False
    assert app_map.is_outgoing(outgoing, 1080) is True


def test_with_an_unknown_screen_width_nothing_is_called_outgoing():
    app_map = parse_app_map(MINIMAL)
    node = UiNode(text="YES", bounds=Bounds(560, 300, 1040, 380))
    assert app_map.is_outgoing(node, 0) is False


def test_selector_strategy_uses_the_declared_selectors():
    data = _minimal(side_strategy="selector")
    data["app_map"]["elements"]["outgoing_bubble"] = {"resource_id": "mine"}
    data["app_map"]["elements"]["incoming_bubble"] = {"resource_id": "theirs"}
    app_map = parse_app_map(data)
    mine = UiNode(resource_id="com.example:id/mine", bounds=Bounds(0, 0, 10, 10))
    theirs = UiNode(resource_id="com.example:id/theirs", bounds=Bounds(0, 0, 10, 10))
    assert app_map.is_outgoing(mine, 1080) is True
    assert app_map.is_outgoing(theirs, 1080) is False


# --- the validation gate -------------------------------------------------


def test_the_shipped_google_messages_map_is_not_marked_validated():
    # It was written from documentation, not confirmed on a phone. If this
    # test ever fails, someone marked it validated -- validated_on must then
    # name the app build it was confirmed against.
    app_map = load_app_map(builtin_map_path("google_messages"), calibrating=True)
    assert app_map.validated is False
    assert app_map.validated_on == ""


def test_an_unvalidated_map_is_refused_unless_the_caller_is_calibrating():
    path = builtin_map_path("google_messages")
    with pytest.raises(UnvalidatedAppMap) as raised:
        load_app_map(path)
    assert "validated" in str(raised.value)
    assert load_app_map(path, calibrating=True).id == "google_messages"


def test_a_validated_map_loads_without_the_calibration_flag(tmp_path):
    body = "\n".join(
        [
            "[app_map]",
            'id = "demo"',
            'package = "com.example.messages"',
            'launch_activity = "com.example.messages.Main"',
            "validated = true",
            'validated_on = "com.example.messages 1.2.3 on Pixel 6a / Android 15"',
            "[app_map.elements]",
            *[f'{name} = {{ resource_id = "{name}" }}' for name in REQUIRED_ELEMENTS],
        ]
    )
    path = tmp_path / "demo.toml"
    path.write_text(body, encoding="utf-8")
    app_map = load_app_map(path)
    assert app_map.validated is True
    assert "Pixel" in app_map.validated_on


def test_a_map_that_is_not_there_says_so():
    with pytest.raises(AppMapError):
        load_app_map("/nonexistent/map.toml")


def test_google_messages_is_among_the_shipped_maps():
    assert "google_messages" in list_app_maps()


# --- the calibration report ---------------------------------------------


def test_calibration_reports_exactly_which_elements_were_not_on_screen():
    app_map = load_app_map(builtin_map_path("google_messages"), calibrating=True)
    screen = parse_ui_dump(
        "<hierarchy rotation='0'><node index='0' text='' resource-id=''"
        " class='android.widget.FrameLayout'"
        " package='com.google.android.apps.messaging'"
        " content-desc='' clickable='false' enabled='true' bounds='[0,0][1080,2340]'>"
        "<node index='0' text='' resource-id='com.google.android.apps.messaging:id/"
        "compose_message_text' class='android.widget.EditText'"
        " package='com.google.android.apps.messaging' content-desc='' clickable='true'"
        " enabled='true' bounds='[40,2100][880,2200]'/></node></hierarchy>"
    )
    absent = missing_on_screen(app_map, screen, ["compose_field", "send_button"])
    assert absent == ["send_button"]


def test_calibration_against_no_screen_reports_everything_absent():
    app_map = load_app_map(builtin_map_path("google_messages"), calibrating=True)
    assert missing_on_screen(app_map, None, ["compose_field"]) == ["compose_field"]
