import itertools

import pytest

from safesound.reply import CALL_DEFLECT, Context, load_world, respond

WORLD = load_world()
OWNER = "Richie"

EXACT_LOCATION = [WORLD["location"]["exact"], "Hiya", "London"]
EVENT_TITLES = [e["title"] for e in WORLD["calendar"]]
ALL_MESSAGE_CONTENT = [m["body"] for m in WORLD["inbox"]] + [m["from"] for m in WORLD["inbox"]] + ["482913"]
SENSITIVE_CONTENT = [m["body"] for m in WORLD["inbox"] if m["sensitive"]] + [
    m["from"] for m in WORLD["inbox"] if m["sensitive"]
] + ["482913"]
NON_SENSITIVE_BODIES = [m["body"] for m in WORLD["inbox"] if not m["sensitive"]]

GIVEAWAY_WORDS = [
    "withh", "hidden", "hide", "sensitive", "private", "confidential", "secret",
    "not allowed", "permission", "can't tell", "cannot tell", "can't share", "restricted",
]

REQUESTS = [
    {"intent": "where_is", "person": None},
    {"intent": "where_is", "person": OWNER},
    {"intent": "is_free", "person": None, "when": None},
    {"intent": "is_free", "person": OWNER, "when": "right now"},
    {"intent": "is_free", "person": None, "when": "tonight"},
    {"intent": "is_free", "person": None, "when": "this afternoon"},
    {"intent": "is_free", "person": None, "when": "today"},
    {"intent": "is_free", "person": None, "when": "at 2pm"},
    {"intent": "read_messages"},
    {"intent": "digest"},
    {"intent": "introduce", "name": "Reuben", "relationship": "friend"},
    {"intent": "leave_message", "to": None, "text": "I stopped by"},
    {"intent": "unclear"},
]


@pytest.fixture
def make_ctx(tmp_path):
    def make(**kwargs):
        defaults = {"world": WORLD, "owner": OWNER, "now": "12:20", "activity_file": tmp_path / "activity.json", "use_llm": False}
        return Context(**{**defaults, **kwargs})
    return make


def ask(make_ctx, request, relationship, channel, room_state, **ctx_kwargs):
    return respond(request, relationship, channel, room_state, make_ctx(**ctx_kwargs))


def assert_absent(text, forbidden):
    for item in forbidden:
        assert item.lower() not in text.lower(), f"{item!r} leaked in: {text!r}"


OUTSIDERS = [
    ("friend", "room", {"speaker_name": "Reuben"}),
    ("friend", "call", {"speaker_name": "Reuben", "caller_id": "Reuben", "verification": "verified"}),
    ("unknown", "room", {}),
    ("unknown", "call", {"caller_id": None, "verification": "unknown_number"}),
    ("unknown", "call", {"caller_id": "Reuben", "verification": "mismatch", "speaker_label": "unknown"}),
]


@pytest.mark.parametrize(("request_", "outsider", "room_state"), list(itertools.product(REQUESTS, OUTSIDERS, ["private", "not_private"])))
def test_outsiders_never_hear_exact_location_events_or_messages(make_ctx, request_, outsider, room_state):
    relationship, channel, ctx_kwargs = outsider
    text = ask(make_ctx, request_, relationship, channel, room_state, **ctx_kwargs)["text"]
    assert_absent(text, EXACT_LOCATION + EVENT_TITLES + ALL_MESSAGE_CONTENT)


@pytest.mark.parametrize(("request_", "relationship"), list(itertools.product(REQUESTS, ["owner", "partner", "friend", "unknown"])))
def test_nobody_hears_private_details_when_room_not_private(make_ctx, request_, relationship):
    text = ask(make_ctx, request_, relationship, "room", "not_private", speaker_name="Someone")["text"]
    assert_absent(text, EXACT_LOCATION + EVENT_TITLES + SENSITIVE_CONTENT)


@pytest.mark.parametrize(("request_", "outsider", "room_state"), list(itertools.product(REQUESTS, OUTSIDERS, ["private", "not_private"])))
def test_refusals_never_hint_that_something_is_hidden(make_ctx, request_, outsider, room_state):
    relationship, channel, ctx_kwargs = outsider
    text = ask(make_ctx, request_, relationship, channel, room_state, **ctx_kwargs)["text"]
    assert_absent(text, GIVEAWAY_WORDS)


@pytest.mark.parametrize("request_", REQUESTS)
def test_partner_never_hears_message_contents(make_ctx, request_):
    text = ask(make_ctx, request_, "partner", "room", "private", speaker_name="Edith")["text"]
    assert_absent(text, ALL_MESSAGE_CONTENT)


def test_owner_private_room_gets_everything(make_ctx):
    reply = ask(make_ctx, {"intent": "read_messages"}, "owner", "room", "private")
    assert reply["text"].startswith("You've got 6 messages.")
    assert "482913" in reply["text"]
    assert reply["disclosed"] == [m["id"] for m in WORLD["inbox"]]
    assert reply["withheld"] == []


def test_owner_not_private_hears_only_non_sensitive(make_ctx):
    reply = ask(make_ctx, {"intent": "read_messages"}, "owner", "room", "not_private")
    for body in NON_SENSITIVE_BODIES:
        assert body in reply["text"]
    assert reply["text"].endswith("Nothing else urgent.")
    assert set(reply["withheld"]) == {m["id"] for m in WORLD["inbox"] if m["sensitive"]}


def test_filtered_reply_is_indistinguishable_from_a_smaller_inbox(make_ctx):
    filtered = ask(make_ctx, {"intent": "read_messages"}, "owner", "room", "not_private")["text"]
    smaller_world = {**WORLD, "inbox": [m for m in WORLD["inbox"] if not m["sensitive"]]}
    genuine = ask(make_ctx, {"intent": "read_messages"}, "owner", "room", "private", world=smaller_world)["text"]
    assert filtered == genuine


def test_non_owner_asking_for_messages(make_ctx):
    reply = ask(make_ctx, {"intent": "read_messages"}, "friend", "room", "private", speaker_name="Reuben")
    assert reply["text"] == "Sorry, I can only do that for Richie."


def test_verified_friend_call_is_greeted_by_name(make_ctx):
    reply = ask(make_ctx, {"intent": "where_is", "person": OWNER}, "friend", "call", "private",
                speaker_name="Reuben", caller_id="Reuben", verification="verified")
    assert reply["text"] == "Hi Reuben, Richie's at work, back around 6. Want me to pass anything on?"
    assert reply["rough"] == ["location"]
    assert reply["disclosed"] == [] and reply["withheld"] == []


def test_partner_gets_exact_location_in_private_room(make_ctx):
    reply = ask(make_ctx, {"intent": "where_is", "person": None}, "partner", "room", "private", speaker_name="Edith")
    assert reply["text"] == "Richie's at Hiya office, London, back around 6."
    assert reply["disclosed"] == ["location"]


@pytest.mark.parametrize("verification", ["unknown_number", "mismatch"])
@pytest.mark.parametrize("request_", [r for r in REQUESTS if r["intent"] in ("where_is", "is_free", "read_messages", "digest")])
def test_unverified_callers_get_the_same_neutral_reply(make_ctx, request_, verification):
    reply = ask(make_ctx, request_, "unknown", "call", "private", caller_id="Reuben", verification=verification)
    assert reply["text"] == CALL_DEFLECT.format(owner=OWNER)
    assert reply["disclosed"] == []


def test_mismatch_is_never_mentioned_to_caller(make_ctx):
    for request_ in REQUESTS:
        text = ask(make_ctx, request_, "unknown", "call", "private", caller_id="Reuben", verification="mismatch")["text"]
        assert_absent(text, ["number", "voice", "match", "verif", "recognis", "Reuben"])


def test_friend_gets_free_busy_without_titles(make_ctx):
    reply = ask(make_ctx, {"intent": "is_free", "person": None, "when": "tonight"}, "friend", "room", "private", speaker_name="Reuben")
    assert reply["text"] == "Richie's busy from 6:30 to 7:30 tonight."
    assert reply["rough"] == ["cal-4"]


def test_owner_gets_event_titles(make_ctx):
    reply = ask(make_ctx, {"intent": "is_free", "person": None, "when": "right now"}, "owner", "room", "private")
    assert reply["text"] == "You're in Dentist appointment until 12:45."
    assert reply["disclosed"] == ["cal-2"]


def test_free_when_nothing_booked(make_ctx):
    reply = ask(make_ctx, {"intent": "is_free", "person": None, "when": "this morning"}, "friend", "room", "private", now="11:00")
    assert reply["text"] == "Richie's busy from 9:30 to 9:45 this morning."
    reply = ask(make_ctx, {"intent": "is_free", "person": None, "when": "at 4pm"}, "friend", "room", "private")
    assert reply["text"] == "Richie's free at 4pm."


def test_unknown_in_room_gets_not_sure(make_ctx):
    assert ask(make_ctx, {"intent": "where_is", "person": None}, "unknown", "room", "private")["text"] == "I'm not sure, sorry."
    assert ask(make_ctx, {"intent": "is_free", "person": None, "when": None}, "unknown", "room", "private")["text"] == "I'm not sure, sorry."


def test_questions_about_other_people_reveal_nothing(make_ctx):
    reply = ask(make_ctx, {"intent": "where_is", "person": "Jordan"}, "owner", "room", "private")
    assert reply["text"] == "I'm not sure, sorry."


def test_leave_message_reply(make_ctx):
    reply = ask(make_ctx, {"intent": "leave_message", "to": None, "text": "call me back"}, "unknown", "call", "private",
                caller_id="Reuben", verification="mismatch")
    assert reply == {"text": "I'll pass that on.", "disclosed": [], "rough": [], "withheld": []}
    reply = ask(make_ctx, {"intent": "leave_message", "to": None, "text": "running late"}, "friend", "call", "private",
                speaker_name="Reuben", caller_id="Reuben", verification="verified")
    assert reply["text"] == "Thanks Reuben, I'll pass that on."


def test_empty_message_asks_what_to_pass_on(make_ctx):
    reply = ask(make_ctx, {"intent": "leave_message", "to": None, "text": ""}, "friend", "room", "private")
    assert reply["text"] == "Sure, what would you like me to pass on?"


def test_unclear_on_call_offers_the_two_safe_options(make_ctx):
    for relationship in ("friend", "unknown"):
        reply = ask(make_ctx, {"intent": "unclear"}, relationship, "call", "private", caller_id="Reuben")
        assert reply == {"text": "Sorry, did you want to know where Richie is, or leave a message?", "disclosed": [], "rough": [], "withheld": []}


def test_unclear_in_room_asks_to_rephrase(make_ctx):
    for relationship in ("owner", "friend", "unknown"):
        reply = ask(make_ctx, {"intent": "unclear"}, relationship, "room", "private")
        assert reply == {"text": "Sorry, could you say that another way?", "disclosed": [], "rough": [], "withheld": []}
