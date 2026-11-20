import time

import numpy as np
import pytest

from safesound.commands import is_echo
from safesound.listener import Listener
from safesound.server import speaking_seconds

LONG_REPLY = (
    "You've got 6 messages. From Northbridge Bank: Your one-time passcode is 482913. It expires in 10 minutes. "
    "We will never ask you to share it. From Riverside Medical Practice: Hi Richie, your blood test results are back. "
    "The doctor would like you to book a follow-up appointment this week to discuss them. From Alex: Can you grab some "
    "milk and bread on the way home? I'll start dinner around seven. From Priya (boss): Please keep this to yourself "
    "for now, but the team restructure is being announced on Friday. Your role is safe. Let's talk tomorrow. "
    "From ParcelGo: Your parcel will be delivered today between 2pm and 4pm. From Jordan: A few of us are playing "
    "five-a-side on Saturday at 10. You in? Nothing else urgent."
)


@pytest.mark.parametrize("heard", [
    "Your blood test results are back.",
    "The doctor would like you to book a follow up appointment this week to discuss them.",
    "From Alex, can you grab some milk and bread on the way home?",
    "from Priya, boss please keep this to yourself for now, but the team restructure is being announced on Friday.",
    "From Parcel Go, your parcel will be delivered today between 2pm and 4pm.",
    "from Jordan, a few of us are playing 5-8 on Saturday at 10.",
])
def test_lines_from_a_long_reply_are_echoes(heard):
    assert is_echo(heard, [LONG_REPLY])


def test_long_replies_get_a_long_quiet_window():
    assert speaking_seconds(LONG_REPLY) > 40
    assert speaking_seconds("I'm not sure, sorry.") < 4


def test_listener_ignores_audio_while_quiet():
    listener = Listener()
    loud = (np.random.default_rng(0).standard_normal(1600) * 3000).astype("<i2").tobytes()
    listener.stay_quiet_for(0.3)
    assert listener.feed(loud) == []
    assert len(listener.pending) == 0
    time.sleep(0.35)
    listener.feed(loud)
    assert len(listener.pending) > 0


def test_quiet_window_only_ever_extends():
    listener = Listener()
    listener.stay_quiet_for(5)
    end = listener.quiet_until
    listener.stay_quiet_for(1)
    assert listener.quiet_until == end
