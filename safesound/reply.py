import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .people import load_people, owner_name
from .policy import allowed, visible_messages

ROOT = Path(__file__).resolve().parent.parent
WORLD_FILE = ROOT / "data" / "world.json"
LEFT_MESSAGES_FILE = ROOT / "data" / "left_messages.json"

NOT_SURE = "I'm not sure, sorry."
CALL_DEFLECT = "{owner} can't take your call right now. Can I take a message?"
CALL_OFFER = "Want me to pass anything on?"
NO_MESSAGES = "No new messages right now."
MESSAGES_END = "Nothing else urgent."
NOTHING_TO_REPORT = "Nothing to report."
PASS_ON = "I'll pass that on."
UNCLEAR_CALL = "Sorry, did you want to know where {owner} is, or leave a message?"
UNCLEAR_ROOM = "Sorry, could you say that another way?"

WINDOWS = {
    "this morning": ("06:00", "12:00"),
    "this afternoon": ("12:00", "17:00"),
    "this evening": ("17:00", "23:59"),
    "tonight": ("17:00", "23:59"),
    "today": (None, "23:59"),
    "later": (None, "23:59"),
}


def load_world(path: Path = WORLD_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class Context:
    speaker_name: str | None = None
    speaker_label: str | None = None
    caller_id: str | None = None
    verification: str = "in_person"
    now: str | None = None
    world: dict | None = None
    owner: str | None = None
    left_messages_file: Path = field(default=LEFT_MESSAGES_FILE)

    def __post_init__(self):
        if self.world is None:
            self.world = load_world()
        if self.owner is None:
            self.owner = owner_name(load_people()) or "the owner"
        if self.now is None:
            self.now = datetime.now().strftime("%H:%M")


def result(text: str, disclosed: list[str] | None = None, withheld: list[str] | None = None) -> dict:
    return {"text": text, "disclosed": disclosed or [], "withheld": withheld or []}


def to_minutes(hhmm: str) -> int:
    hours, mins = hhmm.split(":")
    return int(hours) * 60 + int(mins)


def spoken_time(hhmm: str) -> str:
    hours, mins = (int(x) for x in hhmm.split(":"))
    hour12 = hours % 12 or 12
    return f"{hour12}" if mins == 0 else f"{hour12}:{mins:02d}"


def parse_clock(text: str) -> str | None:
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if not m:
        return None
    hours, mins, half = int(m[1]), int(m[2] or 0), m[3]
    if half == "pm" and hours < 12:
        hours += 12
    if half == "am" and hours == 12:
        hours = 0
    if not half and hours < 8:
        hours += 12
    return f"{hours:02d}:{mins:02d}"


def about_owner(person: str | None, ctx: Context) -> bool:
    return person is None or person.lower() == ctx.owner.lower()


def you_are(relationship: str, ctx: Context) -> str:
    return "You're" if relationship == "owner" else f"{ctx.owner}'s"


def you_have(relationship: str, ctx: Context) -> str:
    return "You've got" if relationship == "owner" else f"{ctx.owner} has"


def is_stranger_on_call(relationship: str, channel: str) -> bool:
    return channel == "call" and relationship == "unknown"


def deflect_call(ctx: Context, withheld: list[str]) -> dict:
    return result(CALL_DEFLECT.format(owner=ctx.owner), withheld=withheld)


def for_channel(reply: dict, relationship: str, channel: str, ctx: Context) -> dict:
    if channel == "call" and relationship in ("friend", "partner") and ctx.speaker_name:
        reply["text"] = f"Hi {ctx.speaker_name}, {reply['text']} {CALL_OFFER}"
    return reply


def where_is(args: dict, relationship: str, channel: str, room_state: str, ctx: Context | None = None) -> dict:
    ctx = ctx or Context()
    if not about_owner(args.get("person"), ctx):
        return for_channel(result(NOT_SURE), relationship, channel, ctx)
    if is_stranger_on_call(relationship, channel):
        return deflect_call(ctx, ["location"])

    location = ctx.world["location"]
    back = f"back around {spoken_time(location['back_by'])}"
    level = allowed(relationship, "location", room_state)
    if level == "full":
        reply = result(f"{you_are(relationship, ctx)} at {location['exact']}, {back}.", disclosed=["location"])
    elif level == "rough":
        reply = result(f"{you_are(relationship, ctx)} {location['rough']}, {back}.", withheld=["location"])
    else:
        reply = result(NOT_SURE, withheld=["location"])
    return for_channel(reply, relationship, channel, ctx)


def events_in(when: str | None, ctx: Context) -> tuple[list[dict], str, bool] | None:
    when = (when or "right now").lower()
    calendar = ctx.world["calendar"]

    if when in ("now", "right now") or when.startswith("at "):
        point = ctx.now if when in ("now", "right now") else parse_clock(when)
        if point is None:
            return None
        p = to_minutes(point)
        hits = [e for e in calendar if to_minutes(e["start"]) <= p < to_minutes(e["end"])]
        return hits, when, True

    if when in WINDOWS:
        start, end = WINDOWS[when]
        lo, hi = to_minutes(start or ctx.now), to_minutes(end)
        hits = [e for e in calendar if to_minutes(e["start"]) < hi and to_minutes(e["end"]) > lo]
        return hits, when, False

    return None


def is_free(args: dict, relationship: str, channel: str, room_state: str, ctx: Context | None = None) -> dict:
    ctx = ctx or Context()
    all_events = [e["id"] for e in ctx.world["calendar"]]
    if not about_owner(args.get("person"), ctx):
        return for_channel(result(NOT_SURE), relationship, channel, ctx)
    if is_stranger_on_call(relationship, channel):
        return deflect_call(ctx, all_events)

    level = allowed(relationship, "calendar", room_state)
    if level == "none":
        return for_channel(result(NOT_SURE, withheld=all_events), relationship, channel, ctx)

    found = events_in(args.get("when"), ctx)
    if found is None:
        return for_channel(result(NOT_SURE), relationship, channel, ctx)
    events, phrase, is_point = found
    ids = [e["id"] for e in events]

    if not events:
        return for_channel(result(f"{you_are(relationship, ctx)} free {phrase}."), relationship, channel, ctx)

    if is_point:
        event = events[0]
        until = spoken_time(event["end"])
        if level == "full":
            text = f"{you_are(relationship, ctx)} in {event['title']} until {until}."
            return for_channel(result(text, disclosed=ids), relationship, channel, ctx)
        text = f"{you_are(relationship, ctx)} busy until {until}."
        return for_channel(result(text, withheld=ids), relationship, channel, ctx)

    spans = [f"from {spoken_time(e['start'])} to {spoken_time(e['end'])}" for e in events]
    if level == "full":
        items = " and ".join(f"{e['title']} {span}" for e, span in zip(events, spans))
        text = f"{you_have(relationship, ctx)} {items} {phrase}."
        return for_channel(result(text, disclosed=ids), relationship, channel, ctx)
    text = f"{you_are(relationship, ctx)} busy {' and '.join(spans)} {phrase}."
    return for_channel(result(text, withheld=ids), relationship, channel, ctx)


def read_messages(args: dict, relationship: str, channel: str, room_state: str, ctx: Context | None = None) -> dict:
    ctx = ctx or Context()
    inbox = ctx.world["inbox"]
    all_ids = [m["id"] for m in inbox]
    if is_stranger_on_call(relationship, channel):
        return deflect_call(ctx, all_ids)
    if relationship != "owner":
        return for_channel(result(f"Sorry, I can only do that for {ctx.owner}.", withheld=all_ids), relationship, channel, ctx)
    if channel == "call":
        return result("I can go through your messages when you're home.", withheld=all_ids)

    shown = visible_messages(inbox, allowed(relationship, "messages", room_state))
    shown_ids = [m["id"] for m in shown]
    withheld = [i for i in all_ids if i not in shown_ids]
    if not shown:
        return result(NO_MESSAGES, withheld=withheld)

    count = f"You've got {len(shown)} message{'s' if len(shown) != 1 else ''}."
    bodies = " ".join(f"From {m['from']}: {m['body']}" for m in shown)
    return result(f"{count} {bodies} {MESSAGES_END}", disclosed=shown_ids, withheld=withheld)


def load_left_messages(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_left_messages(path: Path, messages: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(messages, indent=2, ensure_ascii=False), encoding="utf-8")


def leave_message(args: dict, relationship: str, channel: str, room_state: str, ctx: Context | None = None) -> dict:
    ctx = ctx or Context()
    text = (args.get("text") or "").strip()
    if not text:
        return result("Sure, what would you like me to pass on?")

    stored = load_left_messages(ctx.left_messages_file)
    stored.append({
        "id": f"left-{len(stored) + 1}",
        "time": ctx.now,
        "text": text,
        "to": args.get("to"),
        "from": ctx.speaker_name if relationship != "unknown" else None,
        "voice": ctx.speaker_label,
        "relationship": relationship,
        "channel": channel,
        "caller_id": ctx.caller_id,
        "verification": ctx.verification,
    })
    save_left_messages(ctx.left_messages_file, stored)

    if channel == "call" and relationship in ("friend", "partner") and ctx.speaker_name:
        return result(f"Thanks {ctx.speaker_name}, {PASS_ON[0].lower()}{PASS_ON[1:]}")
    return result(PASS_ON)


def describe_left_message(m: dict) -> str:
    said = f"said: {m['text'].rstrip('.')}."
    if m["channel"] == "call":
        if m["verification"] == "verified":
            return f"{m['from']} called at {spoken_time(m['time'])} and {said}"
        if m["verification"] == "mismatch":
            return (f"Someone called from {m['caller_id']}'s number at {spoken_time(m['time'])}, "
                    f"but it didn't sound like {m['caller_id']}. They {said}")
        return f"Someone called from an unknown number at {spoken_time(m['time'])} and {said}"
    if m["from"]:
        return f"{m['from']} stopped by at {spoken_time(m['time'])} and {said}"
    return f"Someone I didn't recognise stopped by at {spoken_time(m['time'])} and {said}"


def digest(args: dict, relationship: str, channel: str, room_state: str, ctx: Context | None = None) -> dict:
    ctx = ctx or Context()
    stored = load_left_messages(ctx.left_messages_file)
    ids = [m["id"] for m in stored]
    if is_stranger_on_call(relationship, channel):
        return deflect_call(ctx, ids)
    if relationship != "owner":
        return for_channel(result(f"Sorry, I can only do that for {ctx.owner}.", withheld=ids), relationship, channel, ctx)
    if room_state != "private" or not stored:
        return result(NOTHING_TO_REPORT, withheld=ids)

    save_left_messages(ctx.left_messages_file, [])
    return result(" ".join(describe_left_message(m) for m in stored), disclosed=ids)


def introduce(args: dict, relationship: str, channel: str, room_state: str, ctx: Context | None = None) -> dict:
    ctx = ctx or Context()
    if is_stranger_on_call(relationship, channel):
        return deflect_call(ctx, [])
    if relationship != "owner":
        return for_channel(result("Nice to meet you."), relationship, channel, ctx)
    return result("Let's do introductions in person, when you're both here.")


def unclear(args: dict, relationship: str, channel: str, room_state: str, ctx: Context | None = None) -> dict:
    ctx = ctx or Context()
    if channel == "call":
        return result(UNCLEAR_CALL.format(owner=ctx.owner))
    return result(UNCLEAR_ROOM)


REPLIES = {
    "unclear": unclear,
    "where_is": where_is,
    "is_free": is_free,
    "read_messages": read_messages,
    "leave_message": leave_message,
    "digest": digest,
    "introduce": introduce,
}


def respond(command: dict, relationship: str, channel: str, room_state: str, ctx: Context | None = None) -> dict:
    args = {k: v for k, v in command.items() if k != "intent"}
    return REPLIES[command["intent"]](args, relationship, channel, room_state, ctx or Context())
