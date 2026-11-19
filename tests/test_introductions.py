import json

import numpy as np
import pytest

from safesound import speaker
from safesound.commands import parse_command, relationship_in
from safesound.introductions import (
    MAX_ASKS,
    TARGET_SECONDS,
    TIMEOUT_SECONDS,
    Introduction,
    problem_with,
    voice_label,
)
from safesound.people import load_people, lookup
from safesound.speaker import SAMPLE_RATE


@pytest.fixture(autouse=True)
def fake_embed(monkeypatch):
    def embed(chunk):
        vec = np.zeros(192, dtype=np.float32)
        vec[0] = 1.0
        return vec
    monkeypatch.setattr(speaker, "embed", embed)


@pytest.fixture
def files(tmp_path):
    people_file = tmp_path / "people.json"
    people_file.write_text(json.dumps([{"name": "Richie", "relationship": "owner", "voice_file": "voices/owner.npy"}]))
    return people_file, tmp_path / "voices"


def speech(seconds: float, loud: bool = True) -> np.ndarray:
    rng = np.random.default_rng(0)
    amplitude = 0.1 if loud else 0.0
    return (rng.standard_normal(int(seconds * SAMPLE_RATE)) * amplitude).astype(np.float32)


def make(files, name="Reuben", relationship="friend", now=0.0):
    people_file, voices_dir = files
    return Introduction(name, relationship, now, people_file=people_file, voices_dir=voices_dir)


@pytest.mark.parametrize(("text", "relationship"), [
    ("this is my mate Reuben", "friend"),
    ("Meet Reuben, he's a friend.", "friend"),
    ("This is my sister Edith.", "partner"),
    ("Say hi to Jordan, he's my cousin.", "partner"),
])
def test_introduce_phrasings_from_spec_and_family(text, relationship):
    command = parse_command(text)
    assert command["intent"] == "introduce"
    assert command["relationship"] == relationship


@pytest.mark.parametrize(("answer", "relationship"), [
    ("Friend.", "friend"),
    ("He's a mate from work", "friend"),
    ("my best friend", "friend"),
    ("Family", "partner"),
    ("She's my sister", "partner"),
    ("my girlfriend", "partner"),
    ("he's my grandad", "partner"),
    ("um, not sure", None),
    ("", None),
])
def test_relationship_answers(answer, relationship):
    assert relationship_in(answer) == relationship


def test_problem_with_names():
    assert problem_with("Reuben", "Richie") is None
    assert problem_with("Richie", "Richie") == "I already know you, Richie."
    assert problem_with("richie", "Richie") == "I already know you, Richie."
    assert problem_with("Owner", "Richie") == "Sorry, I didn't catch their name."
    assert problem_with("Unknown", "Richie") == "Sorry, I didn't catch their name."
    assert problem_with("", "Richie") == "Sorry, I didn't catch their name."
    assert problem_with(None, "Richie") == "Sorry, I didn't catch their name."


def test_voice_label_is_a_safe_filename():
    assert voice_label("Reuben") == "reuben"
    assert voice_label("O'Brien") == "obrien"
    assert voice_label("Mary-Jane") == "mary-jane"
    assert voice_label("../../etc") == "etc"


def test_known_relationship_goes_straight_to_collecting(files):
    intro = make(files)
    assert intro.stage == "collecting"
    assert intro.opening_line() == "Hi Reuben, could you say a few sentences so I'll recognise you next time?"


def test_missing_relationship_asks_then_maps_answer(files):
    intro = make(files, relationship=None)
    assert intro.stage == "asking"
    assert intro.opening_line() == "Is Reuben a friend or family?"
    line = intro.hear_answer("He's family", now=5)
    assert intro.relationship == "partner"
    assert intro.stage == "collecting"
    assert line == "Hi Reuben, could you say a few sentences so I'll recognise you next time?"
    assert intro.deadline == 5 + TIMEOUT_SECONDS


def test_unrecognised_relationship_is_given_as_family_or_friend_only(files):
    intro = make(files, relationship="boss")
    assert intro.stage == "asking"


def test_unclear_answer_asks_again_then_gives_up(files):
    intro = make(files, relationship=None)
    assert intro.hear_answer("hmm", now=1) == "Sorry, is Reuben a friend or family?"
    for _ in range(MAX_ASKS):
        line = intro.hear_answer("hmm", now=2)
    assert intro.stage == "cancelled"
    assert line == "No problem, we can do that another time."


def test_owner_can_cancel(files):
    intro = make(files, relationship=None)
    assert intro.hear_answer("never mind", now=1) == "No problem, we can do that another time."
    assert intro.stage == "cancelled"


def test_only_collects_new_voices(files):
    intro = make(files)
    assert intro.wants("unknown")
    assert intro.wants("reuben")
    assert not intro.wants("owner")
    assert not intro.wants("edith")


def test_does_not_collect_while_asking(files):
    assert not make(files, relationship=None).wants("unknown")


def test_collects_until_target(files):
    intro = make(files)
    assert not intro.add(speech(TARGET_SECONDS - 1))
    assert intro.add(speech(2))


def test_timeout(files):
    intro = make(files, now=100)
    assert not intro.timed_out(100 + TIMEOUT_SECONDS - 1)
    assert intro.timed_out(100 + TIMEOUT_SECONDS)


def test_finish_saves_voice_and_person(files):
    people_file, voices_dir = files
    intro = make(files)
    intro.add(speech(TARGET_SECONDS))
    assert intro.finish() == "Got it, I'll remember you, Reuben."
    assert intro.stage == "done"
    assert (voices_dir / "reuben.npy").exists()
    assert np.load(voices_dir / "reuben.npy").shape == (192,)
    people = load_people(people_file)
    assert {"name": "Reuben", "relationship": "friend", "voice_file": "voices/reuben.npy"} in people
    assert lookup("reuben", people) == {"name": "Reuben", "relationship": "friend"}
    assert lookup("owner", people) == {"name": "Richie", "relationship": "owner"}


def test_reintroducing_replaces_the_old_entry(files):
    people_file, _ = files
    first = make(files, relationship="friend")
    first.add(speech(TARGET_SECONDS))
    first.finish()
    second = make(files, relationship="partner")
    second.add(speech(TARGET_SECONDS))
    second.finish()
    reubens = [p for p in load_people(people_file) if p["name"] == "Reuben"]
    assert reubens == [{"name": "Reuben", "relationship": "partner", "voice_file": "voices/reuben.npy"}]


def test_too_little_speech_fails_and_saves_nothing(files):
    people_file, voices_dir = files
    intro = make(files)
    intro.add(speech(3))
    assert intro.finish() == "Sorry Reuben, I didn't catch enough to remember you. We can try again later."
    assert intro.stage == "failed"
    assert not (voices_dir / "reuben.npy").exists()
    assert [p["name"] for p in load_people(people_file)] == ["Richie"]


def test_silence_fails(files):
    intro = make(files)
    intro.add(speech(TARGET_SECONDS, loud=False))
    assert intro.finish().startswith("Sorry Reuben")
    assert intro.stage == "failed"


def test_status_for_ui(files):
    intro = make(files)
    intro.add(speech(4))
    assert intro.status() == {
        "type": "introduction", "name": "Reuben", "relationship": "friend",
        "stage": "collecting", "seconds": 4.0, "target": TARGET_SECONDS,
    }
