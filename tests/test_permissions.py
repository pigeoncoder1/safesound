import json

import pytest
from fastapi.testclient import TestClient

from safesound import server
from safesound.people import load_people, permissions_of, update_person
from safesound.policy import allowed, permissions_for
from safesound.reply import Context, load_world, respond

WORLD = load_world()
EVERYTHING = {"messages": "full", "location": "full", "calendar": "full"}
NOTHING = {"messages": "none", "location": "none", "calendar": "none"}


def test_defaults_without_overrides():
    assert permissions_for("friend") == {"messages": "none", "location": "rough", "calendar": "rough"}
    assert permissions_for("partner") == {"messages": "none", "location": "full", "calendar": "full"}


def test_overrides_apply_to_friends_and_partners():
    assert permissions_for("friend", EVERYTHING) == EVERYTHING
    assert permissions_for("partner", NOTHING) == NOTHING
    assert permissions_for("friend", {"location": "full"})["location"] == "full"


@pytest.mark.parametrize("relationship", ["owner", "unknown", "stranger"])
def test_overrides_never_apply_to_owner_or_strangers(relationship):
    assert permissions_for(relationship, NOTHING if relationship == "owner" else EVERYTHING) == permissions_for(relationship)


def test_invalid_override_levels_are_ignored():
    assert permissions_for("friend", {"location": "everything", "messages": None})["location"] == "rough"


def test_room_rule_still_caps_custom_full_access():
    assert allowed("friend", "location", "private", EVERYTHING) == "full"
    assert allowed("friend", "location", "not_private", EVERYTHING) == "rough"
    assert allowed("friend", "messages", "not_private", EVERYTHING) == "rough"


def ctx(**kwargs):
    return Context(world=WORLD, owner="Richie", now="12:20", use_llm=False, **kwargs)


def test_friend_with_exact_location_hears_the_address():
    reply = respond({"intent": "where_is", "person": None}, "friend", "room", "private", ctx(permissions={**NOTHING, "location": "full"}))
    assert reply["text"] == "Richie's at Hiya office, London, back around 6."
    assert reply["disclosed"] == ["location"]


def test_friend_with_no_location_hears_nothing():
    reply = respond({"intent": "where_is", "person": None}, "friend", "room", "private", ctx(permissions=NOTHING))
    assert reply["text"] == "I'm not sure, sorry."


def test_friend_allowed_non_sensitive_messages():
    reply = respond({"intent": "read_messages"}, "friend", "room", "private", ctx(permissions={**NOTHING, "messages": "rough"}))
    assert reply["text"].startswith("Richie has 3 messages.")
    assert "482913" not in reply["text"]
    assert set(reply["withheld"]) == {m["id"] for m in WORLD["inbox"] if m["sensitive"]}


def test_friend_with_all_messages_is_capped_when_room_not_private():
    reply = respond({"intent": "read_messages"}, "friend", "room", "not_private", ctx(permissions=EVERYTHING))
    assert reply["text"].startswith("Richie has 3 messages.")
    assert "482913" not in reply["text"]


def test_messages_are_never_read_over_the_phone_to_others():
    reply = respond({"intent": "read_messages"}, "friend", "call", "private",
                    ctx(permissions=EVERYTHING, speaker_name="Drew", verification="verified"))
    assert reply["text"] == "Hi Drew, I can only go through Richie's messages in person. Want me to pass anything on?"
    assert reply["disclosed"] == []


def test_default_friend_still_refused_messages():
    reply = respond({"intent": "read_messages"}, "friend", "room", "private", ctx())
    assert reply["text"] == "Sorry, I can only do that for Richie."


@pytest.fixture
def people_file(tmp_path):
    path = tmp_path / "people.json"
    path.write_text(json.dumps([
        {"name": "Richie", "relationship": "owner", "voice_file": "voices/owner.npy"},
        {"name": "Drew", "relationship": "friend", "voice_file": "voices/drew.npy"},
    ]))
    return path


def test_update_person_saves_permissions(people_file):
    update_person("drew", None, EVERYTHING, people_file)
    assert permissions_of("drew", load_people(people_file)) == EVERYTHING


def test_changing_relationship_resets_custom_permissions(people_file):
    update_person("drew", None, EVERYTHING, people_file)
    person = update_person("drew", "partner", None, people_file)
    assert person["relationship"] == "partner"
    assert "permissions" not in person


def test_owner_cannot_be_updated(people_file):
    assert update_person("owner", "friend", None, people_file) is None
    assert load_people(people_file)[0]["relationship"] == "owner"


@pytest.fixture
def client(people_file, monkeypatch):
    monkeypatch.setattr(server, "update_person", lambda label, rel, perms: update_person(label, rel, perms, people_file))
    return TestClient(server.app)


def test_patch_permissions(client, people_file):
    before = server.people_changes["version"]
    response = client.patch("/api/people/drew", json={"permissions": {**NOTHING, "location": "full"}})
    assert response.status_code == 200
    assert response.json()["permissions"] == {**NOTHING, "location": "full"}
    assert server.people_changes["version"] == before + 1


def test_patch_relationship(client):
    assert client.patch("/api/people/drew", json={"relationship": "partner"}).json()["relationship"] == "partner"


@pytest.mark.parametrize("body", [
    {"relationship": "owner"},
    {"relationship": "boss"},
    {"permissions": {"messages": "full"}},
    {"permissions": {"messages": "all", "location": "full", "calendar": "full"}},
])
def test_patch_rejects_bad_input(client, body):
    assert client.patch("/api/people/drew", json=body).status_code == 422


def test_patch_owner_refused(client):
    assert client.patch("/api/people/owner", json={"relationship": "friend"}).status_code == 404
