import re

PRONOUNS = {"he", "she", "they", "him", "her", "them"}

PARTNER_WORDS = ["other half", "girlfriend", "boyfriend", "fiancée", "fiancee", "fiancé", "fiance", "partner", "husband", "spouse", "wife"]
FRIEND_WORDS = ["best friend", "friend", "buddy", "mate", "pal"]

WAKE = r"^\s*(?:(?:hey|hi|ok|okay)\s+)?(?:safe\s?sound|earshot)\b[\s,.!?:]*"
PERSON = r"(?P<person>(?-i:[A-Z][\w'-]*)|he|she|they|him|her|them)"
NAME = r"(?-i:[A-Z][\w'-]*)"
REL = "|".join(re.escape(w) for w in PARTNER_WORDS + FRIEND_WORDS)
WHEN = r"(?P<when>right now|now|today|tonight|tomorrow|later|this (?:morning|afternoon|evening|weekend)|at \d{1,2}(?::\d{2})?\s*(?:am|pm)?)"

INTRODUCE = [
    re.compile(rf"\b(?:this is|meet|here'?s|say (?:hello|hi) to)\s+my\s+(?P<rel>{REL})\s*,?\s*(?P<name>{NAME})", re.I),
    re.compile(
        rf"\b(?:this is|meet|here'?s|say (?:hello|hi) to)\s+(?P<name>{NAME})\b"
        rf"(?:\s*[,.]?\s*(?:(?:he|she|they)(?:'s|'re| is| are)|who'?s|is)?\s*(?:a|an|my|our)?\s*(?P<rel>{REL})\b)?",
        re.I,
    ),
]

LEAVE_MESSAGE = [
    re.compile(
        rf"^(?:(?:can|could|would|will) you\s+|please\s+)*(?:tell|let)\s+{PERSON}\s+(?:know\s+)?(?:that\s+)?(?P<text>.+)$",
        re.I,
    ),
    re.compile(
        rf"\b(?:leave|take|pass on)\s+a\s+message(?:\s+for\s+{PERSON})?\s*[:,.]?\s*(?:saying\s+|that\s+)?(?P<text>.*)$",
        re.I,
    ),
]

DIGEST = re.compile(
    r"\b(?:anything (?:happen|happened|new|i should know)"
    r"|what (?:did i|have i) miss"
    r"|did (?:anyone|anybody) (?:stop|come|drop|pop) (?:by|round|over)"
    r"|did (?:anyone|anybody) (?:call|visit|ask (?:for|about|after) me)"
    r"|(?:any|were there any) (?:visitors|callers)"
    r"|who (?:came|stopped|dropped|popped) (?:by|round|over)"
    r"|while i was (?:out|away|gone))",
    re.I,
)

READ_MESSAGES = [
    re.compile(r"\b(?:read|check|play|what are|go through)\b.*\b(?:messages?|texts?|inbox|emails?)\b", re.I),
    re.compile(r"\b(?:any|got any|have i got any|do i have any)\s+(?:new\s+)?(?:messages?|texts?|emails?)\b", re.I),
]

IS_FREE = re.compile(
    rf"\bis\s+{PERSON}\s+(?:free|busy|available|doing anything|up to anything)\b(?:\s+{WHEN})?",
    re.I,
)

WHERE_IS = [
    re.compile(rf"\bwhere(?:'s|\s+is|\s+has)\s+{PERSON}\b", re.I),
    re.compile(rf"\bwhere\s+{PERSON}\s+is\b", re.I),
    re.compile(rf"\bis\s+{PERSON}\s+(?:home|at home|in|out|back|around|there|about)\b", re.I),
    re.compile(rf"\b(?:speak|talk)\s+(?:to|with)\s+{PERSON}\b", re.I),
    re.compile(rf"\bput\s+{PERSON}\s+on\b", re.I),
    re.compile(rf"\bwhen\s+(?:will|is)\s+{PERSON}\s+(?:be\s+)?(?:back|home)\b", re.I),
]


def person_or_owner(word: str | None) -> str | None:
    if not word or word.lower() in PRONOUNS:
        return None
    return word


def relationship_from(word: str | None) -> str | None:
    if not word:
        return None
    word = word.lower()
    if word in PARTNER_WORDS:
        return "partner"
    if word in FRIEND_WORDS:
        return "friend"
    return None


def clean_message(text: str) -> str:
    return text.strip().rstrip(".!?").strip()


def parse_command(text: str) -> dict | None:
    if not text:
        return None
    text = re.sub(WAKE, "", text.strip(), flags=re.I)

    for pattern in INTRODUCE:
        if m := pattern.search(text):
            return {"intent": "introduce", "name": m["name"], "relationship": relationship_from(m["rel"])}

    for pattern in LEAVE_MESSAGE:
        if m := pattern.search(text):
            return {"intent": "leave_message", "to": person_or_owner(m["person"]), "text": clean_message(m["text"])}

    if DIGEST.search(text):
        return {"intent": "digest"}

    if any(p.search(text) for p in READ_MESSAGES):
        return {"intent": "read_messages"}

    if m := IS_FREE.search(text):
        return {"intent": "is_free", "person": person_or_owner(m["person"]), "when": m["when"].lower() if m["when"] else None}

    for pattern in WHERE_IS:
        if m := pattern.search(text):
            return {"intent": "where_is", "person": person_or_owner(m["person"])}

    return None
