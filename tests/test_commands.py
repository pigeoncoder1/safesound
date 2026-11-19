import pytest

from safesound.commands import parse_command


@pytest.mark.parametrize("text", [
    "Read my messages.",
    "Any messages?",
    "Do I have any messages?",
    "Have I got any new texts?",
    "Can you check my messages please?",
    "Safesound, read me my messages.",
    "What are my messages?",
])
def test_read_messages(text):
    assert parse_command(text) == {"intent": "read_messages"}


@pytest.mark.parametrize(("text", "person"), [
    ("Where's Sam?", "Sam"),
    ("Where is Richie?", "Richie"),
    ("Where is she?", None),
    ("Where's he got to?", None),
    ("Do you know where Sam is?", "Sam"),
    ("Is Sam home?", "Sam"),
    ("When will she be back?", None),
    ("Hey Safe Sound, where's Richie?", "Richie"),
    ("Is Sam there?", "Sam"),
    ("Hi, is Richie there please?", "Richie"),
    ("Can I speak to Sam?", "Sam"),
    ("Could I talk to Richie please?", "Richie"),
    ("I'd like to speak with Sam.", "Sam"),
    ("Is Sam around?", "Sam"),
    ("Is she about?", None),
    ("Can you put Sam on?", "Sam"),
])
def test_where_is(text, person):
    assert parse_command(text) == {"intent": "where_is", "person": person}


@pytest.mark.parametrize(("text", "person", "when"), [
    ("Is Sam free tonight?", "Sam", "tonight"),
    ("Is she busy?", None, None),
    ("Is Richie available this afternoon?", "Richie", "this afternoon"),
    ("Is he doing anything tomorrow?", None, "tomorrow"),
    ("Is Sam free at 3pm?", "Sam", "at 3pm"),
    ("is she free right now", None, "right now"),
])
def test_is_free(text, person, when):
    assert parse_command(text) == {"intent": "is_free", "person": person, "when": when}


@pytest.mark.parametrize(("text", "to", "message"), [
    ("Tell Sam I stopped by.", "Sam", "I stopped by"),
    ("Can you tell her I'll be late tonight?", None, "I'll be late tonight"),
    ("Could you tell Richie that the parcel arrived", "Richie", "the parcel arrived"),
    ("Please let Sam know I called.", "Sam", "I called"),
    ("Leave a message for Sam: running ten minutes late.", "Sam", "running ten minutes late"),
    ("Can I leave a message saying I'll call back?", None, "I'll call back"),
])
def test_leave_message(text, to, message):
    assert parse_command(text) == {"intent": "leave_message", "to": to, "text": message}


@pytest.mark.parametrize(("text", "name", "relationship"), [
    ("Earshot, this is Reuben, he's a friend.", "Reuben", "friend"),
    ("Safesound, this is Edith, she's my partner.", "Edith", "partner"),
    ("This is my partner Edith.", "Edith", "partner"),
    ("Meet Jordan, my best friend.", "Jordan", "friend"),
    ("This is Alex, my girlfriend.", "Alex", "partner"),
    ("Say hello to Reuben, he's a mate.", "Reuben", "friend"),
    ("This is Reuben.", "Reuben", None),
])
def test_introduce(text, name, relationship):
    assert parse_command(text) == {"intent": "introduce", "name": name, "relationship": relationship}


@pytest.mark.parametrize("text", [
    "Anything happen?",
    "Did anyone stop by?",
    "What did I miss?",
    "Did anybody call while I was out?",
    "Were there any visitors?",
    "Who came by?",
    "Did anyone ask for me?",
])
def test_digest(text):
    assert parse_command(text) == {"intent": "digest"}


@pytest.mark.parametrize("text", [
    "",
    "Thank you.",
    "What's the weather like?",
    "This is great.",
    "Where is it?",
    "I need to tell you something",
    "Is it raining?",
])
def test_no_match(text):
    assert parse_command(text) is None
