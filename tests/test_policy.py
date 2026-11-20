import json
from pathlib import Path

import pytest

from safesound.policy import PERMISSIONS, allowed, visible_messages

EXPECTED_PRIVATE = {
    ("owner", "messages"): "full",
    ("owner", "location"): "full",
    ("owner", "calendar"): "full",
    ("partner", "messages"): "full",
    ("partner", "location"): "full",
    ("partner", "calendar"): "full",
    ("friend", "messages"): "rough",
    ("friend", "location"): "rough",
    ("friend", "calendar"): "rough",
    ("unknown", "messages"): "none",
    ("unknown", "location"): "none",
    ("unknown", "calendar"): "none",
}

EXPECTED_NOT_PRIVATE = {
    ("owner", "messages"): "rough",
    ("owner", "location"): "rough",
    ("owner", "calendar"): "rough",
    ("partner", "messages"): "rough",
    ("partner", "location"): "rough",
    ("partner", "calendar"): "rough",
    ("friend", "messages"): "rough",
    ("friend", "location"): "rough",
    ("friend", "calendar"): "rough",
    ("unknown", "messages"): "none",
    ("unknown", "location"): "none",
    ("unknown", "calendar"): "none",
}

INBOX = [
    {"id": 1, "sensitive": True},
    {"id": 2, "sensitive": False},
    {"id": 3, "sensitive": True},
    {"id": 4, "sensitive": False},
]


@pytest.mark.parametrize(("relationship", "info_type"), EXPECTED_PRIVATE)
def test_private_room(relationship, info_type):
    assert allowed(relationship, info_type, "private") == EXPECTED_PRIVATE[(relationship, info_type)]


@pytest.mark.parametrize(("relationship", "info_type"), EXPECTED_NOT_PRIVATE)
def test_not_private_room(relationship, info_type):
    assert allowed(relationship, info_type, "not_private") == EXPECTED_NOT_PRIVATE[(relationship, info_type)]


def test_table_has_every_combination():
    assert {(r, i) for r, row in PERMISSIONS.items() for i in row} == set(EXPECTED_PRIVATE)


def test_owner_hears_only_non_sensitive_messages_when_not_private():
    level = allowed("owner", "messages", "not_private")
    assert [m["id"] for m in visible_messages(INBOX, level)] == [2, 4]


def test_owner_hears_everything_when_private():
    level = allowed("owner", "messages", "private")
    assert [m["id"] for m in visible_messages(INBOX, level)] == [1, 2, 3, 4]


def test_no_messages_for_none_level():
    assert visible_messages(INBOX, "none") == []


def test_unrecognised_relationship_is_treated_as_unknown():
    for info_type in ("messages", "location", "calendar"):
        assert allowed("stranger", info_type, "private") == "none"


def test_not_private_room_never_gives_full_to_anyone():
    for relationship in PERMISSIONS:
        for info_type in ("messages", "location", "calendar"):
            assert allowed(relationship, info_type, "not_private") != "full"


def test_not_private_room_never_increases_access():
    order = {"none": 0, "rough": 1, "full": 2}
    for relationship in PERMISSIONS:
        for info_type in ("messages", "location", "calendar"):
            private = allowed(relationship, info_type, "private")
            not_private = allowed(relationship, info_type, "not_private")
            assert order[not_private] <= order[private]


def test_unknown_room_state_is_treated_as_not_private():
    for info_type in ("messages", "location", "calendar"):
        assert allowed("owner", info_type, "something_else") == "rough"


def test_unknown_info_type_raises():
    with pytest.raises(ValueError):
        allowed("owner", "bank_balance", "private")


def test_world_inbox_has_six_messages_with_sensitive_flags():
    world_file = Path(__file__).resolve().parent.parent / "data" / "world.json"
    if not world_file.exists():
        pytest.skip("data/world.json not present")
    inbox = json.loads(world_file.read_text(encoding="utf-8"))["inbox"]
    assert len(inbox) == 6
    assert all(isinstance(m["sensitive"], bool) for m in inbox)
