import json

import pytest

from safesound import activity, llm
from safesound.activity import (
    deliver_digest,
    load_activity,
    log_interaction,
    mark_delivered,
    summarise,
    template_summary,
    undelivered,
)
from safesound.commands import parse_command
from safesound.reply import Context, load_world, respond

SPEC_FIELDS = {"time", "channel", "caller_id", "voice", "verification", "heard", "intent",
               "earshot_said", "message_left", "delivered"}


@pytest.fixture
def log_file(tmp_path):
    return tmp_path / "activity.json"


def log(log_file, **overrides):
    entry = {
        "channel": "call", "caller_id": "Reuben", "voice": "reuben", "name": "Reuben",
        "relationship": "friend", "verification": "verified", "heard": "Where's Richie?",
        "intent": "where_is", "earshot_said": "Hi Reuben, Richie's at work, back around 6. Want me to pass anything on?",
        "disclosed": [], "message_left": None, "time": "15:00",
    }
    return log_interaction(**{**entry, **overrides}, path=log_file)


def spec_example(log_file):
    log(log_file, earshot_said="Richie's at work, back around 6.")
    log(log_file, time="15:02", heard="Tell him I'll be late tonight", intent="leave_message",
        earshot_said="Thanks Reuben, I'll pass that on.", message_left="I'll be late tonight")
    log(log_file, time="15:05", voice="unknown", name=None, relationship="unknown", verification="mismatch",
        earshot_said="Richie can't take your call right now. Can I take a message?")
    return load_activity(log_file)


def test_entry_has_all_spec_fields(log_file):
    entry = log(log_file)
    assert SPEC_FIELDS <= set(entry)
    assert entry["delivered"] is False
    assert entry["id"] == "act-1"
    assert log(log_file)["id"] == "act-2"
    assert len(load_activity(log_file)) == 2


def test_mark_delivered(log_file):
    log(log_file)
    log(log_file)
    mark_delivered(["act-1"], log_file)
    assert [e["id"] for e in undelivered(load_activity(log_file))] == ["act-2"]


def test_spec_example_template(log_file):
    entries = spec_example(log_file)
    assert summarise(entries, use_llm=False) == (
        'Reuben called at 3 and asked where you were and left a message: "I\'ll be late tonight". '
        'I said: "Richie\'s at work, back around 6." '
        "Someone also called from Reuben's number at 3:05, but it didn't sound like Reuben, "
        "so I didn't tell them anything. They asked where you were."
    )


def test_unknown_number_caller(log_file):
    entries = [log(log_file, caller_id=None, voice="unknown", name=None, relationship="unknown",
                   verification="unknown_number", earshot_said="Richie can't take your call right now. Can I take a message?")]
    assert summarise(entries, use_llm=False) == (
        "Someone called from an unknown number at 3 and asked where you were. I didn't tell them anything."
    )


def test_unknown_visitor_who_left_a_message(log_file):
    entries = [log(log_file, channel="room", caller_id=None, voice="unknown", name=None, relationship="unknown",
                   verification="in_person", intent="leave_message", message_left="I popped round",
                   earshot_said="I'll pass that on.", time="14:30")]
    assert summarise(entries, use_llm=False) == (
        'Someone I didn\'t recognise was here at 2:30 and left a message: "I popped round".'
    )


def test_friend_in_room_unclear(log_file):
    entries = [log(log_file, channel="room", caller_id=None, verification="in_person", intent="unclear",
                   earshot_said="Sorry, could you say that another way?")]
    assert summarise(entries, use_llm=False) == "Reuben was here at 3, but I couldn't tell what they wanted."


def test_mismatch_alone_is_not_also(log_file):
    entries = [log(log_file, voice="unknown", name=None, relationship="unknown", verification="mismatch")]
    assert summarise(entries, use_llm=False).startswith("Someone called from Reuben's number at 3")


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def __call__(self, system, user, max_tokens=300):
        self.calls.append((system, user))
        return self.reply


def test_llm_rephrases_but_mismatch_is_always_kept(log_file, monkeypatch):
    fake = FakeLLM("Reuben rang at three asking where you were, and I told him you're at work. He'll be late tonight.")
    monkeypatch.setattr(llm, "complete", fake)
    text = summarise(spec_example(log_file))
    assert text.startswith("Reuben rang at three")
    assert "Someone also called from Reuben's number at 3:05, but it didn't sound like Reuben" in text


def test_llm_cannot_drop_the_mismatch(log_file, monkeypatch):
    monkeypatch.setattr(llm, "complete", FakeLLM("Nothing much happened."))
    text = summarise(spec_example(log_file))
    assert "didn't sound like Reuben" in text


def test_llm_only_sees_the_activity_log(log_file, monkeypatch):
    fake = FakeLLM("Reuben rang.")
    monkeypatch.setattr(llm, "complete", fake)
    summarise(spec_example(log_file))
    system, user = fake.calls[0]
    world = json.dumps(load_world())
    for secret in ("Hiya", "London", "482913", "Dentist", "Northbridge"):
        assert secret in world
        assert secret not in system and secret not in user
    assert user.startswith("Activity log: ")
    assert "mismatch" not in user


@pytest.mark.parametrize("bad_reply", [None, "", "x" * 5000])
def test_bad_llm_output_falls_back_to_template(log_file, monkeypatch, bad_reply):
    monkeypatch.setattr(llm, "complete", FakeLLM(bad_reply))
    entries = spec_example(log_file)
    assert summarise(entries) == summarise(entries, use_llm=False)


def test_long_logs_are_shortened(log_file):
    entries = [log(log_file, session=f"call-{i}") for i in range(12)]
    normal, _ = template_summary(entries)
    assert normal.endswith("There were 4 more after that.")


def test_deliver_digest_marks_everything_delivered(log_file):
    spec_example(log_file)
    text, ids = deliver_digest(log_file, use_llm=False)
    assert ids == ["act-1", "act-2", "act-3"]
    assert "Reuben called at 3" in text
    assert undelivered(load_activity(log_file)) == []
    assert deliver_digest(log_file, use_llm=False) is None


def ctx(log_file, **kwargs):
    return Context(world=load_world(), owner="Richie", now="16:00", activity_file=log_file, use_llm=False, **kwargs)


def test_owner_asks_for_digest_in_private_room(log_file):
    spec_example(log_file)
    reply = respond({"intent": "digest"}, "owner", "room", "private", ctx(log_file))
    assert reply["text"].startswith("Reuben called at 3 and asked where you were and left a message")
    assert "didn't sound like Reuben" in reply["text"]
    assert reply["disclosed"] == ["act-1", "act-2", "act-3"]
    assert respond({"intent": "digest"}, "owner", "room", "private", ctx(log_file))["text"] == "Nothing to report."


def test_digest_waits_while_room_not_private(log_file):
    spec_example(log_file)
    reply = respond({"intent": "digest"}, "owner", "room", "not_private", ctx(log_file))
    assert reply["text"] == "Nothing to report."
    assert len(undelivered(load_activity(log_file))) == 3


@pytest.mark.parametrize(("relationship", "channel"), [("friend", "room"), ("partner", "room"), ("unknown", "room")])
def test_only_owner_gets_digest(log_file, relationship, channel):
    spec_example(log_file)
    reply = respond({"intent": "digest"}, relationship, channel, "private", ctx(log_file, speaker_name="Edith"))
    assert reply["text"] == "Sorry, I can only do that for Richie."
    assert "Reuben" not in reply["text"]
    assert len(undelivered(load_activity(log_file))) == 3


def test_unverified_caller_asking_for_digest_gets_deflected(log_file):
    spec_example(log_file)
    reply = respond({"intent": "digest"}, "unknown", "call", "private", ctx(log_file, caller_id="Richie", verification="mismatch"))
    assert reply["text"] == "Richie can't take your call right now. Can I take a message?"


@pytest.mark.parametrize("text", ["Anything happen?", "Did I miss anything?", "Who called?", "Any calls?",
                                  "Who was here?", "What did I miss?"])
def test_digest_phrasings(text):
    assert parse_command(text) == {"intent": "digest"}


def test_quotes_drop_call_greeting_and_offer(log_file):
    entries = [log(log_file)]
    assert summarise(entries, use_llm=False) == (
        "Reuben called at 3 and asked where you were. I said: \"Richie's at work, back around 6.\""
    )


def test_one_impostor_call_is_one_sentence(log_file):
    impostor = {"voice": "owner", "name": None, "relationship": "unknown", "verification": "mismatch", "session": "call-1"}
    log(log_file, **impostor, intent="unclear", heard="Hi there.")
    log(log_file, **impostor, intent="where_is", heard="Is Richie there please?")
    text = summarise(load_activity(log_file), use_llm=False)
    assert text == ("Someone called from Reuben's number at 3, but it didn't sound like Reuben, "
                    "so I didn't tell them anything. They asked where you were.")


def test_separate_calls_are_not_merged(log_file):
    log(log_file, session="call-1")
    log(log_file, session="call-2", time="16:00")
    text = summarise(load_activity(log_file), use_llm=False)
    assert text.count("Reuben called") == 2
