import pytest

from safesound import calls
from safesound.calls import (
    call_status,
    current_call,
    effective_relationship,
    end_call,
    start_call,
    verify_caller,
)

PEOPLE = [
    {"name": "Richie", "relationship": "owner", "voice_file": "voices/owner.npy"},
    {"name": "Reuben", "relationship": "friend", "voice_file": "voices/reuben.npy"},
    {"name": "Edith", "relationship": "partner", "voice_file": "voices/edith.npy"},
]


@pytest.fixture(autouse=True)
def no_call_left_over():
    calls.end_call()
    yield
    calls.end_call()


def test_verified_when_number_and_voice_match():
    assert verify_caller("Reuben", "reuben", PEOPLE) == "verified"
    assert effective_relationship("Reuben", "reuben", PEOPLE) == "friend"


def test_caller_id_is_case_insensitive():
    assert verify_caller("reuben", "reuben", PEOPLE) == "verified"


def test_mismatch_reubens_number_strangers_voice():
    assert verify_caller("Reuben", "unknown", PEOPLE) == "mismatch"
    assert effective_relationship("Reuben", "unknown", PEOPLE) == "unknown"


def test_mismatch_reubens_number_other_known_voice():
    assert verify_caller("Reuben", "edith", PEOPLE) == "mismatch"
    assert effective_relationship("Reuben", "edith", PEOPLE) == "unknown"


def test_unknown_number():
    assert verify_caller(None, "unknown", PEOPLE) == "unknown_number"
    assert effective_relationship(None, "unknown", PEOPLE) == "unknown"


def test_known_voice_from_unknown_number_is_still_unknown():
    assert verify_caller(None, "reuben", PEOPLE) == "unknown_number"
    assert effective_relationship(None, "reuben", PEOPLE) == "unknown"


def test_number_not_in_contacts_is_unknown_number():
    assert verify_caller("Dave", "reuben", PEOPLE) == "unknown_number"
    assert effective_relationship("Dave", "reuben", PEOPLE) == "unknown"


def test_pending_until_caller_speaks():
    assert verify_caller("Reuben", None, PEOPLE) == "pending"
    assert effective_relationship("Reuben", None, PEOPLE) == "unknown"


def test_start_and_end_call():
    assert current_call() is None
    call = start_call("Reuben")
    assert current_call() is call
    assert call.caller_id == "Reuben"
    assert call.voice_labels == []
    assert end_call() is call
    assert current_call() is None


def test_blank_caller_id_means_no_caller_id():
    assert start_call("  ").caller_id is None


def test_only_one_call_at_a_time():
    start_call("Reuben")
    with pytest.raises(RuntimeError):
        start_call("Edith")


def test_end_call_with_no_call_is_harmless():
    assert end_call() is None


def test_call_status_follows_latest_voice():
    assert call_status(PEOPLE)["active"] is False
    call = start_call("Reuben")
    assert call_status(PEOPLE)["verification"] == "pending"
    call.voice_labels.append("reuben")
    assert call_status(PEOPLE) == {
        "type": "call", "active": True, "caller_id": "Reuben", "voice": "reuben", "verification": "verified",
    }
    call.voice_labels.append("unknown")
    assert call_status(PEOPLE)["verification"] == "mismatch"
