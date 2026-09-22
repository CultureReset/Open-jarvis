"""Fixtures for the phone driver tests.

Everything here is MOCK-BASED. The fake phone renders screens and applies
taps in process; it exercises the procedure's logic and its evidence rules
and says nothing about a real device. None of these tests satisfies a
physical-device acceptance gate.
"""

from __future__ import annotations

import pytest

from openjarvis.phone.appmap import builtin_map_path, load_app_map
from openjarvis.phone.device import PhoneDevice
from openjarvis.phone.messages import InboxWatcher, MessagesProcedure
from tests.phone.fake_phone import FakePhone


@pytest.fixture
def phone() -> FakePhone:
    return FakePhone()


@pytest.fixture
def messages_map():
    # calibrating=True because the shipped map is deliberately unvalidated.
    return load_app_map(builtin_map_path("google_messages"), calibrating=True)


@pytest.fixture
def device(phone: FakePhone) -> PhoneDevice:
    return PhoneDevice(phone.serial, phone, settle=0.0)


@pytest.fixture
def procedure(device: PhoneDevice, messages_map) -> MessagesProcedure:
    return MessagesProcedure(device, messages_map, step_pause=0.0, observe_pause=0.0)


@pytest.fixture
def watcher(procedure: MessagesProcedure) -> InboxWatcher:
    return InboxWatcher(procedure)
