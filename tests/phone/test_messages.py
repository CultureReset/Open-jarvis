"""The texting procedure, and the evidence it demands before saying 'sent'.

MOCK-BASED. The phone here is a simulator; it proves the procedure's logic
and its evidence rules and nothing about a real device. See fake_phone.py.
"""

from __future__ import annotations

from openjarvis.phone.device import is_screen_verb
from openjarvis.phone.messages import (
    NOT_SENT,
    SENT,
    UNCERTAIN,
    ScreenMessage,
    align_new,
)

NUMBER = "+12515551234"
OTHER = "+12515559999"
BODY = "Approve the 40 ft charter Saturday 7am, $850? Reply YES"


# --- sending -------------------------------------------------------------


def test_a_send_works_the_screen_and_reports_the_evidence(procedure, phone):
    outcome = procedure.send(NUMBER, BODY)
    assert outcome.status == SENT
    assert outcome.ok
    assert phone.threads[NUMBER].bubbles[-1].body == BODY
    assert phone.threads[NUMBER].bubbles[-1].outgoing is True
    # The last line of evidence is what was actually seen, not what was done.
    assert "outgoing bubble" in outcome.evidence[-1]


def test_sending_issues_only_screen_verbs(procedure, phone):
    procedure.send(NUMBER, BODY)
    assert phone.refused == []
    assert all(is_screen_verb(command) for command in phone.commands)
    assert any(command.startswith("input tap") for command in phone.commands)
    assert any(command.startswith("input text") for command in phone.commands)


def test_the_message_is_typed_rather_than_injected(procedure, phone):
    procedure.send(NUMBER, "Reply YES")
    typed = [c for c in phone.commands if c.startswith("input text")]
    assert "input text 'Reply%sYES'" in typed


def test_a_number_that_is_not_e164_is_never_typed(procedure, phone):
    for bad in ("2515551234", "", "+1 251 555 1234", "hello"):
        outcome = procedure.send(bad, BODY)
        assert outcome.status == NOT_SENT
        assert "E.164" in outcome.evidence[-1]
    assert phone.commands == []


def test_an_empty_message_is_refused_before_anything_is_tapped(procedure, phone):
    outcome = procedure.send(NUMBER, "   ")
    assert outcome.status == NOT_SENT
    assert phone.commands == []


def test_a_detached_phone_stops_the_send_at_the_first_step(procedure, phone):
    phone.attached = False
    outcome = procedure.send(NUMBER, BODY)
    assert outcome.status == NOT_SENT
    assert "not attached" in outcome.evidence[-1]


def test_typed_is_not_assumed_arrived_the_field_is_read_back(
    procedure, phone, monkeypatch
):
    # The keyboard bridge swallows the body: the compose field never holds
    # the message, so nothing is sent.
    original = phone._type_raw
    monkeypatch.setattr(
        phone,
        "_type_raw",
        lambda text: None if phone.focus == "compose" else original(text),
    )
    outcome = procedure.send(NUMBER, BODY)
    assert outcome.status == NOT_SENT
    assert "never held the intended text" in outcome.evidence[-1]
    assert not phone.threads.get(NUMBER) or not phone.threads[NUMBER].bubbles


def test_a_phone_that_takes_no_typing_at_all_sends_nothing(procedure, phone):
    phone.swallow_typing = True
    outcome = procedure.send(NUMBER, BODY)
    assert outcome.status == NOT_SENT
    # It stops at the recipient, which is the earliest point it can.
    assert "could not open a conversation" in outcome.evidence[-1]
    assert phone.threads == {}


def test_a_truncated_body_is_abandoned_rather_than_sent_garbled(procedure, phone):
    phone.drop_after = 10
    outcome = procedure.send(NUMBER, BODY)
    assert outcome.status == NOT_SENT
    assert not phone.threads.get(NUMBER, None) or not phone.threads[NUMBER].bubbles


def test_a_recipient_the_field_did_not_take_stops_the_send(
    procedure, phone, monkeypatch
):
    original = phone._type_raw

    def only_recipient_is_dropped(text: str) -> None:
        if phone.focus == "recipient":
            return
        original(text)

    monkeypatch.setattr(phone, "_type_raw", only_recipient_is_dropped)
    outcome = procedure.send(NUMBER, BODY)
    assert outcome.status == NOT_SENT
    assert "could not open a conversation" in outcome.evidence[-1]


def test_a_failure_marker_on_screen_means_not_sent(procedure, phone):
    phone.send_fails = True
    outcome = procedure.send(NUMBER, BODY)
    assert outcome.status == NOT_SENT
    assert "not send" in outcome.evidence[-1].lower()


def test_a_tap_that_lands_but_shows_nothing_is_uncertain_not_sent(
    procedure, phone, monkeypatch
):
    # The send button takes the tap and the app does nothing visible. That is
    # neither a success nor a clean failure, and it is reported as neither.
    monkeypatch.setattr(phone, "_send", lambda: None)
    outcome = procedure.send(NUMBER, BODY)
    assert outcome.status == UNCERTAIN
    assert not outcome.ok
    assert "uncertain" in outcome.evidence[-1]


def test_a_body_containing_a_quote_still_goes_through_verified(procedure, phone):
    body = "Owner's approval needed: 40 ft charter. Reply YES"
    assert procedure.send(NUMBER, body).status == SENT
    assert phone.threads[NUMBER].bubbles[-1].body == body


def test_the_compose_field_is_cleared_before_retyping(procedure, phone):
    phone.screen_name = "thread"
    phone.open_thread = NUMBER
    phone.threads[NUMBER] = phone.threads.get(NUMBER) or __import__(
        "tests.phone.fake_phone", fromlist=["Thread"]
    ).Thread(name=NUMBER)
    phone.compose = "half typed draft"
    assert procedure.send(NUMBER, BODY).status == SENT
    assert phone.threads[NUMBER].bubbles[-1].body == BODY


# --- reading -------------------------------------------------------------


def test_the_conversation_list_is_read_off_the_screen(procedure, phone):
    phone.receive(NUMBER, "Can you do Saturday?")
    phone.receive(OTHER, "Any slips open?")
    assert procedure.open_app() is True
    rows = procedure.list_conversations()
    assert {row.name for row in rows} == {NUMBER, OTHER}
    assert "Can you do Saturday?" in next(
        row.preview for row in rows if row.name == NUMBER
    )


def test_a_thread_read_tells_the_two_sides_apart(procedure, phone):
    procedure.send(NUMBER, BODY)
    phone.receive(NUMBER, "YES")
    messages = procedure.read_conversation(NUMBER)
    assert [(message.body, message.outgoing) for message in messages] == [
        (BODY, True),
        ("YES", False),
    ]


def test_reading_a_conversation_that_is_not_on_the_list_yields_nothing(procedure):
    assert procedure.read_conversation("+15005550000") == []


def test_a_fingerprint_separates_direction_and_text():
    incoming = ScreenMessage(conversation=NUMBER, body="YES", outgoing=False)
    outgoing = ScreenMessage(conversation=NUMBER, body="YES", outgoing=True)
    other = ScreenMessage(conversation=OTHER, body="YES", outgoing=False)
    later = ScreenMessage(
        conversation=NUMBER, body="YES", outgoing=False, timestamp_text="2m"
    )
    assert (
        len(
            {
                incoming.fingerprint,
                outgoing.fingerprint,
                other.fingerprint,
                later.fingerprint,
            }
        )
        == 4
    )
    assert (
        incoming.fingerprint
        == ScreenMessage(conversation=NUMBER, body="YES", outgoing=False).fingerprint
    )


# --- alignment: an overlapping read must not replay an approval ----------


def test_overlapping_reads_emit_only_the_tail():
    assert align_new(["a", "b"], ["a", "b", "c"])[0] == 2
    assert align_new(["a", "b", "c"], ["b", "c", "d"])[0] == 2


def test_an_unchanged_screen_emits_nothing():
    start, _ = align_new(["a", "b"], ["a", "b"])
    assert start == 2


def test_a_scrolled_view_that_shows_only_old_messages_emits_nothing():
    start, _ = align_new(["a", "b", "c", "d"], ["c", "d"])
    assert start == 2


def test_two_identical_replies_are_both_seen():
    start, _ = align_new(["yes"], ["yes", "yes"])
    assert start == 1


def test_losing_the_overlap_emits_nothing_rather_than_risking_a_replay():
    start, note = align_new(["a", "b", "c"], ["x", "y"])
    assert start == 2
    assert "replay" in note


def test_an_empty_screen_emits_nothing():
    assert align_new(["a"], [])[0] == 0


# --- the inbox watcher ---------------------------------------------------


def test_baseline_records_history_without_emitting_it(procedure, phone, watcher):
    phone.receive(NUMBER, "old message")
    assert watcher.baseline() == 1
    assert watcher.poll() == []


def test_a_reply_after_baseline_is_seen_once(procedure, phone, watcher):
    procedure.send(NUMBER, BODY)
    watcher.baseline()
    phone.receive(NUMBER, "YES")
    first = watcher.poll()
    assert [message.body for message in first] == ["YES"]
    assert first[0].conversation == NUMBER
    assert watcher.poll() == []


def test_two_identical_replies_are_both_reported(procedure, phone, watcher):
    procedure.send(NUMBER, BODY)
    watcher.baseline()
    phone.receive(NUMBER, "YES")
    assert [m.body for m in watcher.poll()] == ["YES"]
    phone.receive(NUMBER, "YES")
    assert [m.body for m in watcher.poll()] == ["YES"]
    assert watcher.poll() == []


def test_a_conversation_from_a_new_number_is_reported_in_full(
    procedure, phone, watcher
):
    watcher.baseline()
    phone.receive(OTHER, "Do you have a slip open Friday?")
    assert [m.body for m in watcher.poll()] == ["Do you have a slip open Friday?"]


def test_the_agents_own_messages_are_never_reported_as_inbound(
    procedure, phone, watcher
):
    watcher.baseline()
    procedure.send(NUMBER, BODY)
    assert watcher.poll() == []


def test_polling_without_a_baseline_treats_the_first_poll_as_one(
    procedure, phone, watcher
):
    phone.receive(NUMBER, "history nobody has read")
    assert watcher.baselined is False
    assert watcher.poll() == []
    assert watcher.baselined is True
    phone.receive(NUMBER, "YES")
    assert [m.body for m in watcher.poll()] == ["YES"]


def test_watching_issues_only_screen_verbs(procedure, phone, watcher):
    watcher.baseline()
    phone.receive(NUMBER, "YES")
    watcher.poll()
    assert phone.refused == []
    assert all(is_screen_verb(command) for command in phone.commands)


def test_conversations_beyond_the_prime_limit_are_recorded_not_emitted(
    procedure, phone
):
    from openjarvis.phone.messages import InboxWatcher

    for index in range(4):
        phone.receive(f"+1251555{index:04d}", f"message {index}")
    watcher = InboxWatcher(procedure, prime_limit=2)
    assert watcher.baseline() == 4
    # A change in a conversation that was never read is recorded rather than
    # emitted; the reply after that is seen.
    phone.receive("+12515550003", "YES")
    assert watcher.poll() == []
    phone.receive("+12515550003", "YES again")
    assert [m.body for m in watcher.poll()] == ["YES again"]


# --- no provider ever appears in this path -------------------------------


def test_no_cloud_sms_provider_appears_anywhere_in_the_phone_package():
    import pathlib

    import openjarvis.phone as package

    root = pathlib.Path(package.__file__).parent
    vendors = (
        "twilio",
        "sendblue",
        "messagebird",
        "vonage",
        "plivo",
        "bandwidth",
        "telnyx",
        "sinch",
    )
    for path in sorted(root.rglob("*.py")) + sorted(root.rglob("*.toml")):
        source = path.read_text(encoding="utf-8").lower()
        for vendor in vendors:
            assert vendor not in source, f"{vendor} appears in {path.name}"


def test_the_driver_never_names_an_sms_send_api_or_the_message_database():
    import pathlib

    import openjarvis.phone as package

    root = pathlib.Path(package.__file__).parent
    forbidden = (
        "service call",
        "content://sms",
        "content query",
        "mmssms.db",
        "sms_body",
        "smsto:",
        "sendtextmessage",
    )
    for path in sorted(root.rglob("*.py")) + sorted(root.rglob("*.toml")):
        source = path.read_text(encoding="utf-8")
        lowered = source.lower()
        for phrase in forbidden:
            if phrase not in lowered:
                continue
            # Naming one to forbid it is allowed; using one is not. Every
            # occurrence must be in prose, not in code.
            for line_number, line in enumerate(source.splitlines(), start=1):
                if phrase in line.lower():
                    assert _is_prose(source, line_number), (
                        f"{phrase!r} is used as code in {path.name}:{line_number}"
                    )


def _is_prose(source: str, line_number: int) -> bool:
    """True when this line sits inside a comment or a docstring."""
    import io
    import tokenize

    stripped = source.splitlines()[line_number - 1].lstrip()
    if stripped.startswith("#"):
        return True
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError):
        return False
    for token in tokens:
        if token.type not in (tokenize.STRING, tokenize.COMMENT):
            continue
        if token.start[0] <= line_number <= token.end[0]:
            return True
    return False
