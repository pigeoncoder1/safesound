from safesound.room import RoomState

COOLDOWN = 180


def make_room() -> RoomState:
    return RoomState(cooldown_seconds=COOLDOWN, unknown_chunks_to_flip=2)


def test_empty_room_is_private():
    room = make_room()
    assert room.state(0) == "private"
    assert room.voices_present(0) == []


def test_owner_alone_stays_private():
    room = make_room()
    for t in (0, 5, 10, 15):
        room.observe("owner", t)
    assert room.state(16) == "private"


def test_one_stray_unknown_stays_private():
    room = make_room()
    room.observe("owner", 0)
    room.observe("unknown", 5)
    room.observe("owner", 10)
    assert room.state(11) == "private"


def test_unknowns_separated_by_owner_do_not_flip():
    room = make_room()
    room.observe("unknown", 0)
    room.observe("owner", 5)
    room.observe("unknown", 10)
    assert room.state(11) == "private"


def test_two_unknowns_in_a_row_flip():
    room = make_room()
    room.observe("owner", 0)
    room.observe("unknown", 5)
    assert room.state(6) == "private"
    room.observe("unknown", 10)
    assert room.state(11) == "not_private"


def test_owner_speaking_does_not_cancel_confirmed_unknown():
    room = make_room()
    room.observe("unknown", 0)
    room.observe("unknown", 5)
    room.observe("owner", 10)
    assert room.state(11) == "not_private"


def test_cooldown_expires():
    room = make_room()
    room.observe("unknown", 0)
    room.observe("unknown", 5)
    assert room.state(5 + COOLDOWN - 1) == "not_private"
    assert room.state(5 + COOLDOWN) == "private"


def test_more_unknowns_restart_cooldown():
    room = make_room()
    room.observe("unknown", 0)
    room.observe("unknown", 5)
    room.observe("unknown", 100)
    assert room.state(5 + COOLDOWN + 1) == "not_private"
    assert room.state(100 + COOLDOWN) == "private"


def test_owner_last_heard():
    room = make_room()
    assert room.owner_last_heard(0) is None
    room.observe("owner", 10)
    room.observe("trusted", 20)
    assert room.owner_last_heard(25) == 15
    room.observe("owner", 30)
    assert room.owner_last_heard(32) == 2


def test_voices_present_most_recent_first_and_expire():
    room = make_room()
    room.observe("owner", 0)
    room.observe("trusted", 50)
    assert room.voices_present(60) == [
        {"label": "trusted", "last_heard_seconds_ago": 10},
        {"label": "owner", "last_heard_seconds_ago": 60},
    ]
    assert room.voices_present(COOLDOWN + 10) == [
        {"label": "trusted", "last_heard_seconds_ago": COOLDOWN - 40},
    ]
