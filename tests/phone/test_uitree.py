"""Parsing the screen, and finding things on it."""

from __future__ import annotations

from openjarvis.phone.uitree import (
    Selector,
    find,
    find_all,
    parse_bounds,
    parse_ui_dump,
    texts,
)

DUMP = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout"
        package="com.example.app" content-desc="" clickable="false" enabled="true"
        focused="false" scrollable="false" bounds="[0,0][1080,2340]">
    <node index="0" text="" resource-id="" class="android.widget.LinearLayout"
          package="com.example.app" content-desc="" clickable="true" enabled="true"
          bounds="[0,300][1080,480]">
      <node index="0" text="Reef Runner Charters"
            resource-id="com.example.app:id/row_name"
            class="android.widget.TextView" package="com.example.app"
            content-desc="" clickable="false" enabled="true"
            bounds="[40,310][700,370]"/>
      <node index="1" text="Saturday at 7" resource-id="com.example.app:id/row_snippet"
            class="android.widget.TextView" package="com.example.app" content-desc=""
            clickable="false" enabled="true" bounds="[40,380][900,440]"/>
    </node>
    <node index="1" text="" resource-id="com.example.app:id/fab"
          class="android.widget.ImageButton" package="com.example.app"
          content-desc="Start chat" clickable="true" enabled="true"
          bounds="[900,2100][1040,2240]"/>
    <node index="2" text="hidden" resource-id="com.example.app:id/gone"
          class="android.widget.TextView" package="com.example.app" content-desc=""
          clickable="false" enabled="true" bounds="[0,0][0,0]"/>
  </node>
</hierarchy>
UI hierchary dumped to: /sdcard/ng-screen.xml
"""


def test_bounds_parse_and_give_a_centre():
    bounds = parse_bounds("[40,310][700,370]")
    assert (bounds.width, bounds.height) == (660, 60)
    assert bounds.center == (370, 340)


def test_unparseable_bounds_are_empty_rather_than_an_exception():
    assert parse_bounds("nonsense").is_empty()
    assert parse_bounds("").is_empty()


def test_adb_trailing_noise_does_not_stop_the_parse():
    root = parse_ui_dump(DUMP)
    assert root is not None
    assert root.cls == "android.widget.FrameLayout"


def test_no_tree_in_the_output_is_reported_as_none():
    assert parse_ui_dump("") is None
    assert parse_ui_dump("ERROR: could not get idle state.") is None
    assert parse_ui_dump("<hierarchy rotation='0'><node") is None


def test_an_empty_hierarchy_is_none_not_a_phantom_screen():
    assert parse_ui_dump("<hierarchy rotation='0'></hierarchy>") is None


def test_resource_id_matches_on_a_suffix_so_maps_skip_the_package():
    root = parse_ui_dump(DUMP)
    assert find(root, Selector(resource_id="row_name")).text == "Reef Runner Charters"
    assert find(root, Selector(resource_id="com.example.app:id/row_name")) is not None
    assert find(root, Selector(resource_id="row")) is None


def test_contains_matches_ignore_case_but_exact_matches_do_not():
    root = parse_ui_dump(DUMP)
    assert find(root, Selector(content_desc_contains="start CHAT")) is not None
    assert find(root, Selector(content_desc="start chat")) is None
    assert find(root, Selector(content_desc="Start chat")) is not None


def test_class_matches_on_a_suffix():
    root = parse_ui_dump(DUMP)
    assert find(root, Selector(cls="ImageButton")) is not None
    assert find(root, Selector(cls="android.widget.ImageButton")) is not None
    assert find(root, Selector(cls="Button")) is None


def test_several_selectors_act_as_alternatives_for_a_renamed_view():
    root = parse_ui_dump(DUMP)
    found = find(root, Selector(resource_id="send_button"), Selector(resource_id="fab"))
    assert found is not None and found.content_desc == "Start chat"


def test_nodes_with_no_area_are_not_on_screen():
    root = parse_ui_dump(DUMP)
    assert find(root, Selector(resource_id="gone")) is None
    assert find(root, Selector(resource_id="gone"), visible_only=False) is not None


def test_results_come_back_in_reading_order():
    root = parse_ui_dump(DUMP)
    labels = texts(find_all(root, Selector(cls="TextView")))
    assert labels == ["Reef Runner Charters", "Saturday at 7"]


def test_a_label_resolves_to_the_row_that_takes_the_tap():
    root = parse_ui_dump(DUMP)
    label = find(root, Selector(resource_id="row_name"))
    host = label.nearest_clickable()
    assert host.cls == "android.widget.LinearLayout"
    assert host.center == (540, 390)


def test_a_clickable_node_is_its_own_tap_target():
    root = parse_ui_dump(DUMP)
    fab = find(root, Selector(resource_id="fab"))
    assert fab.nearest_clickable() is fab


def test_label_prefers_text_and_falls_back_to_the_description():
    root = parse_ui_dump(DUMP)
    assert find(root, Selector(resource_id="row_name")).label == "Reef Runner Charters"
    assert find(root, Selector(resource_id="fab")).label == "Start chat"


def test_an_empty_selector_is_recognised_as_empty():
    assert Selector().is_empty()
    assert not Selector(text="x").is_empty()


def test_unknown_selector_fields_are_rejected_rather_than_ignored():
    import pytest

    with pytest.raises(ValueError) as raised:
        Selector.from_dict({"resource-id": "fab"})
    assert "resource-id" in str(raised.value)


def test_multiple_windows_in_one_dump_are_all_kept():
    two = DUMP.replace(
        "</hierarchy>",
        '<node index="1" text="Allow" resource-id="android:id/button1"'
        ' class="android.widget.Button" package="android" content-desc=""'
        ' clickable="true" enabled="true" bounds="[600,1200][900,1300]"/></hierarchy>',
    )
    root = parse_ui_dump(two)
    assert find(root, Selector(text="Allow")) is not None
    assert find(root, Selector(resource_id="row_name")) is not None
