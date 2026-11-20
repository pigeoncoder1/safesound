import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from safesound import server
from safesound.activity import clear_activity, load_activity, log_interaction
from safesound.people import load_people, remove_person


@pytest.fixture
def files(tmp_path):
    voices = tmp_path / "voices"
    voices.mkdir()
    for label in ("owner", "drew", "edith"):
        np.save(voices / f"{label}.npy", np.zeros(192, dtype=np.float32))
    people_file = tmp_path / "people.json"
    people_file.write_text(json.dumps([
        {"name": "Richie", "relationship": "owner", "voice_file": "voices/owner.npy"},
        {"name": "Drew", "relationship": "friend", "voice_file": "voices/drew.npy"},
        {"name": "Edith", "relationship": "partner", "voice_file": "voices/edith.npy"},
    ]))
    return voices, people_file, tmp_path / "activity.json"


def test_remove_person_deletes_entry_and_voice(files):
    voices, people_file, _ = files
    assert remove_person("drew", voices, people_file)["name"] == "Drew"
    assert [p["name"] for p in load_people(people_file)] == ["Richie", "Edith"]
    assert not (voices / "drew.npy").exists()
    assert (voices / "edith.npy").exists()


def test_owner_cannot_be_removed(files):
    voices, people_file, _ = files
    assert remove_person("owner", voices, people_file) is None
    assert (voices / "owner.npy").exists()
    assert len(load_people(people_file)) == 3


def test_unknown_label_removes_nothing(files):
    voices, people_file, _ = files
    assert remove_person("../owner", voices, people_file) is None
    assert remove_person("nobody", voices, people_file) is None
    assert len(load_people(people_file)) == 3


def test_clear_activity(files):
    *_, log_file = files
    for _ in range(3):
        log_interaction(channel="room", caller_id=None, voice="drew", name="Drew", relationship="friend",
                        verification="in_person", heard="hi", intent="where_is", earshot_said="ok",
                        disclosed=[], message_left=None, path=log_file)
    assert clear_activity(log_file) == 3
    assert load_activity(log_file) == []
    assert clear_activity(log_file) == 0


@pytest.fixture
def client(files, monkeypatch):
    voices, people_file, log_file = files
    monkeypatch.setattr(server, "remove_person", lambda label, _voices: remove_person(label, voices, people_file))
    monkeypatch.setattr(server, "clear_activity", lambda: clear_activity(log_file))
    return TestClient(server.app)


def test_delete_person_endpoint(client, files):
    _, people_file, _ = files
    before = server.people_changes["version"]
    response = client.delete("/api/people/drew")
    assert response.status_code == 200
    assert response.json() == {"removed": "Drew"}
    assert server.people_changes["version"] == before + 1
    assert "Drew" not in [p["name"] for p in load_people(people_file)]


def test_delete_owner_endpoint_refused(client):
    before = server.people_changes["version"]
    assert client.delete("/api/people/owner").status_code == 404
    assert server.people_changes["version"] == before


def test_clear_activity_endpoint(client, files):
    *_, log_file = files
    log_interaction(channel="call", caller_id="Drew", voice="drew", name="Drew", relationship="friend",
                    verification="verified", heard="hi", intent="leave_message", earshot_said="ok",
                    disclosed=[], message_left="running late", path=log_file)
    assert client.delete("/api/activity").json() == {"cleared": 1}
    assert load_activity(log_file) == []
