import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from safesound import owner_setup as owner_setup_module
from safesound import server, speaker
from safesound.owner_setup import TARGET_SECONDS, OwnerSetup, clean_name, owner_enrolled, set_owner
from safesound.people import load_people
from safesound.speaker import SAMPLE_RATE


@pytest.fixture(autouse=True)
def fake_embed(monkeypatch):
    def embed(chunk):
        vec = np.zeros(192, dtype=np.float32)
        vec[1] = 1.0
        return vec
    monkeypatch.setattr(speaker, "embed", embed)


@pytest.fixture
def paths(tmp_path):
    people_file = tmp_path / "people.json"
    people_file.write_text(json.dumps([
        {"name": "Richie", "relationship": "owner", "voice_file": "voices/owner.npy"},
        {"name": "Drew", "relationship": "friend", "voice_file": "voices/drew.npy"},
    ]))
    return {"voices_dir": tmp_path / "voices", "people_file": people_file, "enroll_dir": tmp_path / "enroll"}


def frames(seconds: float, loud: bool = True) -> list[bytes]:
    rng = np.random.default_rng(1)
    audio = rng.standard_normal(int(seconds * SAMPLE_RATE)) * (0.1 if loud else 0.0)
    pcm = (audio * 32767).astype("<i2")
    return [pcm[i:i + 1600].tobytes() for i in range(0, len(pcm), 1600)]


@pytest.mark.parametrize(("raw", "expected"), [
    ("Richie", "Richie"),
    ("  Mary   Jane ", "Mary Jane"),
    ("richie", "Richie"),
    ("mary jane", "Mary Jane"),
    ("O'Brien", "O'Brien"),
    ("", None),
    ("1234", None),
    ("../etc", None),
    ("x" * 40, None),
    (None, None),
])
def test_clean_name(raw, expected):
    assert clean_name(raw) == expected


def test_set_owner_replaces_old_owner_and_keeps_others(paths):
    people = set_owner("Sam", paths["people_file"])
    assert people[0] == {"name": "Sam", "relationship": "owner", "voice_file": "voices/owner.npy"}
    assert [p["name"] for p in people] == ["Sam", "Drew"]
    assert sum(p["relationship"] == "owner" for p in load_people(paths["people_file"])) == 1


def test_set_owner_removes_a_friend_with_the_same_name(paths):
    people = set_owner("Drew", paths["people_file"])
    assert people == [{"name": "Drew", "relationship": "owner", "voice_file": "voices/owner.npy"}]


def test_recording_finishes_at_target(paths):
    setup = OwnerSetup("Richie", **paths)
    chunks = frames(TARGET_SECONDS)
    assert not any(setup.add(c) for c in chunks[:-1])
    assert setup.add(chunks[-1])


def test_finish_saves_voice_recording_and_owner(paths):
    setup = OwnerSetup("Sam", **paths)
    for chunk in frames(TARGET_SECONDS):
        setup.add(chunk)
    assert setup.finish() == "All set, Sam. I'll recognise your voice from now on."
    assert setup.stage == "done"
    assert np.load(paths["voices_dir"] / "owner.npy").shape == (192,)
    assert (paths["enroll_dir"] / "owner.wav").exists()
    assert owner_enrolled(paths["voices_dir"], paths["people_file"])
    assert load_people(paths["people_file"])[0]["name"] == "Sam"


def test_silence_fails_and_changes_nothing(paths):
    setup = OwnerSetup("Sam", **paths)
    for chunk in frames(TARGET_SECONDS, loud=False):
        setup.add(chunk)
    assert setup.finish().startswith("I couldn't hear enough speech")
    assert setup.stage == "failed"
    assert not (paths["voices_dir"] / "owner.npy").exists()
    assert load_people(paths["people_file"])[0]["name"] == "Richie"


def test_owner_enrolled_needs_both_voice_and_person(paths):
    assert not owner_enrolled(paths["voices_dir"], paths["people_file"])
    paths["voices_dir"].mkdir()
    np.save(paths["voices_dir"] / "owner.npy", np.zeros(192, dtype=np.float32))
    assert owner_enrolled(paths["voices_dir"], paths["people_file"])
    paths["people_file"].write_text("[]")
    assert not owner_enrolled(paths["voices_dir"], paths["people_file"])


def test_progress_is_throttled(paths):
    setup = OwnerSetup("Sam", **paths)
    due = []
    for chunk in frames(2.0):
        setup.add(chunk)
        due.append(setup.progress_due())
    assert sum(due) == 4


def test_setup_over_the_websocket(paths, monkeypatch):
    monkeypatch.setattr(server, "OwnerSetup", lambda name: OwnerSetup(name, **paths))
    received = []
    with TestClient(server.app).websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "owner_setup_start", "name": "1234"}))
        while (e := ws.receive_json())["type"] != "owner_setup":
            pass
        assert e["stage"] == "failed"

        ws.send_text(json.dumps({"type": "owner_setup_start", "name": "Sam"}))
        for chunk in frames(TARGET_SECONDS):
            ws.send_bytes(chunk)
        while True:
            e = ws.receive_json()
            received.append(e["type"])
            if e["type"] == "owner_setup" and e["stage"] in ("done", "failed"):
                break
    assert e["stage"] == "done"
    assert e["name"] == "Sam"
    assert load_people(paths["people_file"])[0]["name"] == "Sam"
    assert "transcript" not in received and "voice" not in received


def test_demo_endpoint_reports_setup(monkeypatch):
    monkeypatch.setattr(server, "owner_enrolled", lambda: False)
    data = TestClient(server.app).get("/api/demo").json()
    assert data["owner_enrolled"] is False
    assert data["setup"]["seconds"] == TARGET_SECONDS
    assert data["setup"]["prompt"] == owner_setup_module.ENROL_PROMPT
