# `openjarvis.phone` — the phone that is part of the box

The Android plugged into the box is a component of the machine, not a user's
handset. It has its own SIM and its own number, and the agent uses it the way
a hand does: it opens an app, taps, types, and reads what is on the screen.

There is no SMS send API here, no message database read, and no third-party
messaging provider. That is not a convention — it is enforced in code, and
tested.

## What is in here

| Module | What it is |
| --- | --- |
| `device.py` | The hand and the eyes. `ScreenOnlyShell` allowlists screen verbs; `PhoneDevice` taps, types, presses, and reads the screen under a lock. |
| `uitree.py` | The screen, parsed from `uiautomator dump`, with selectors that find things and give back the point to touch. |
| `appmap.py` | Per-app screen knowledge as data, plus the gate that keeps an unconfirmed map off a live phone. |
| `data/*.toml` | The App Maps themselves. |
| `messages.py` | The texting procedure and its evidence rules. |

`openjarvis.channels.android_sim` is the thin adapter that wires this to
OpenJarvis's channel contract. It builds no device commands itself.

## The allowlist

`ScreenOnlyShell.shell()` matches every command against
`PERMITTED_COMMANDS` and raises `ForbiddenDeviceCommand` on anything else.
Taps, swipes, keyevents, `input text`, `uiautomator dump` to one fixed path,
`am start` on an app's own MAIN/LAUNCHER activity, and a handful of read-only
`getprop`/`wm size`/`dumpsys package` probes. Nothing more.

So these cannot be issued, and there are tests for each:

- `service call isms …` — sends an SMS with no UI involved at all.
- `content query --uri content://sms/…` — reads the message database instead
  of the screen.
- `am start … -d sms:…` or `--es sms_body …` — pre-fills a message through an
  intent rather than typing it.
- `pm grant`, `su`, `settings put` — widening what the device allows.

Opening an app is the one thing done by name rather than by hunting an icon:
`am start` on its MAIN/LAUNCHER activity, which is what the launcher does
when an icon is tapped. Everything after that — which conversation, which
field, which words, which button — is found on screen and reached by
coordinate.

## The evidence rules

SMS is used here to authorize real actions, so the procedure will not claim
more than the screen showed.

**Typed is not the same as intended.** `input text` cannot represent every
character — it reads `%s` as a space and has no escape for a single quote or
a literal `%s`. So the body is typed and then read back out of the compose
field and compared. A mismatch clears the field, retries once, and then
abandons the send. A garbled message is bad; a garbled authorization request
is worse.

**Tapped send is not the same as sent.** `MessagesProcedure.send` returns
`sent` only when the compose field has emptied *and* the words are visible in
an outgoing bubble in that thread, with no failure marker on screen.
Otherwise it returns `uncertain`, and `uncertain` is reported as uncertain —
never as success and never as a clean failure. Every outcome carries the
`evidence` lines that produced it.

**A reply is only what the screen shows.** `InboxWatcher` notices a change in
a conversation's row on the list, opens that thread, reads the bubbles, and
aligns them against the previous read of the same thread. Where the overlap
cannot be established it emits nothing rather than risk re-emitting an old
`YES` and re-authorizing a spend.

## App Maps and the validation gate

An App Map is execution knowledge, not reasoning. It names each element the
procedure needs — `compose_field`, `send_button`, `message_bubble` — as an
ordered list of selectors, best first, so a build that renamed a view is
covered by a fallback. The procedure itself contains no app-specific names.

A map is a claim about a specific app version, and a wrong claim means a tap
landing somewhere unintended. So each map carries `validated` and
`validated_on`, and `load_app_map` refuses an unvalidated map unless the
caller says it is calibrating. `AndroidSimChannel.connect()` therefore fails
with a clear reason rather than driving a phone with selectors nobody has
confirmed.

**`data/google_messages.toml` is marked `validated = false` on purpose.** Its
selectors were written from public view identifiers and have not been
confirmed on a device.

## Calibrating a map on the real phone

```
export NG_ANDROID_SERIAL=<the box's phone>

jarvis phone maps                  # which maps exist, and their state
jarvis phone screen                # what is on screen, with selector ids
jarvis phone calibrate --map google_messages
```

`calibrate` walks the conversation list, a new-conversation screen and an
open thread, and reports per screen which named elements it could not find.
Fix those selectors against `jarvis phone screen`, run it again, and when it
comes back clean set `validated = true` and put the app build in
`validated_on`.

Nothing marks a map validated automatically. That is a claim about hardware,
and only a person who watched it happen can make it.

## Testing

`tests/phone/` and `tests/cli/test_phone_cmd.py` run against
`tests/phone/fake_phone.py`, a simulator that renders screens as
`uiautomator dump` XML and applies taps to them. Every command it receives
still passes through `is_screen_verb`, so the tests do check that the driver
issues nothing but screen verbs.

**These are mock-based tests and satisfy no physical-device acceptance gate.**
Selector correctness, timing, keyboard behaviour and whether a carrier
accepted anything are only answerable on the phone.
