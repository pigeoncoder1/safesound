import json
import re
from pathlib import Path

from . import llm
from .clock import now_hhmm, spoken_time

ACTIVITY_FILE = Path(__file__).resolve().parent.parent / "data" / "activity.json"
MAX_ENTRIES_SPOKEN = 8
MAX_REPHRASE_GROWTH = 1.5

ASKED = {
    "where_is": "asked where you were",
    "is_free": "asked whether you were free",
    "read_messages": "asked about your messages",
    "digest": "asked what had been happening",
    "introduce": "tried to introduce someone",
}
ANSWERED = {"where_is", "is_free"}

REPHRASE_PROMPT = """You make a draft summary sound natural when spoken aloud to the owner of a personal assistant.
Address the owner as "you" and turn quoted replies into reported speech ("I said you were at work").
Keep every fact in the draft: who, when, what they asked, what the assistant told them, and every message.
Do not add anything that is not in the draft. Do not mention technical details such as verification.
Do not guess anyone's gender: use their name or "they". Be as short as the draft or shorter.
Reply with the rewritten summary only."""


def load_activity(path: Path = ACTIVITY_FILE) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_activity(entries: list[dict], path: Path = ACTIVITY_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def log_interaction(*, channel: str, caller_id: str | None, voice: str, name: str | None, relationship: str,
                    verification: str, heard: str, intent: str, earshot_said: str, disclosed: list[str],
                    message_left: str | None, session: str | None = None, time: str | None = None,
                    path: Path = ACTIVITY_FILE) -> dict:
    entries = load_activity(path)
    entry = {
        "id": f"act-{len(entries) + 1}",
        "time": time or now_hhmm(),
        "channel": channel,
        "session": session,
        "caller_id": caller_id,
        "voice": voice,
        "name": name,
        "relationship": relationship,
        "verification": verification,
        "heard": heard,
        "intent": intent,
        "earshot_said": earshot_said,
        "disclosed": disclosed,
        "message_left": message_left,
        "delivered": False,
    }
    entries.append(entry)
    save_activity(entries, path)
    return entry


def clear_activity(path: Path = ACTIVITY_FILE) -> int:
    count = len(load_activity(path))
    save_activity([], path)
    return count


def undelivered(entries: list[dict]) -> list[dict]:
    return [e for e in entries if not e["delivered"]]


def mark_delivered(ids: list[str], path: Path = ACTIVITY_FILE) -> None:
    entries = load_activity(path)
    for e in entries:
        if e["id"] in ids:
            e["delivered"] = True
    save_activity(entries, path)


def who_and_when(e: dict, also: bool = False) -> str:
    t = spoken_time(e["time"])
    someone = "Someone also" if also else "Someone"
    if e["channel"] == "call":
        if e["verification"] == "verified":
            return f"{e['name']} called at {t}"
        if e["verification"] == "mismatch":
            return f"{someone} called from {e['caller_id']}'s number at {t}, but it didn't sound like {e['caller_id']}"
        if e["caller_id"]:
            return f"{someone} called at {t} from a number listed as {e['caller_id']} that I don't know"
        return f"{someone} called from an unknown number at {t}"
    if e["name"]:
        return f"{e['name']} was here at {t}"
    return f"{someone} I didn't recognise was here at {t}"


def spoken_core(said: str) -> str:
    from .reply import CALL_OFFER
    said = re.sub(r"^Hi [^,]+, ", "", said or "")
    return said.removesuffix(CALL_OFFER).strip()


def group_key(e: dict) -> tuple:
    return e["channel"], e.get("session"), e["caller_id"], e["voice"], e["verification"]


def grouped(entries: list[dict]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    for e in entries:
        if groups and group_key(groups[-1][-1]) == group_key(e):
            groups[-1].append(e)
        else:
            groups.append([e])
    return groups


def joined(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def actions_of(group: list[dict]) -> list[str]:
    actions: list[str] = []
    for e in group:
        if e["message_left"]:
            actions.append(f'left a message: "{e["message_left"]}"')
        elif e["intent"] in ASKED and ASKED[e["intent"]] not in actions:
            actions.append(ASKED[e["intent"]])
    return actions


def describe(group: list[dict], also: bool = False) -> str:
    first = group[0]
    who = who_and_when(first, also)
    actions = actions_of(group)
    asked_something = any(e["intent"] in ASKED for e in group)

    if first["verification"] == "mismatch":
        parts = [f"{who}, so I didn't tell them anything."]
        if actions:
            parts.append(f"They {joined(actions)}.")
        return " ".join(parts)

    parts = [f"{who} and {joined(actions)}." if actions else f"{who}, but I couldn't tell what they wanted."]
    if first["relationship"] in ("unknown", None):
        if asked_something:
            parts.append("I didn't tell them anything.")
        return " ".join(parts)

    answers: list[str] = []
    for e in group:
        core = spoken_core(e["earshot_said"])
        if e["intent"] in ANSWERED and core and core not in answers:
            answers.append(core)
    parts += [f'I said: "{a}"' for a in answers]
    return " ".join(parts)


def template_summary(entries: list[dict]) -> tuple[str, str]:
    normal = grouped([e for e in entries if e["verification"] != "mismatch"])
    mismatches = grouped([e for e in entries if e["verification"] == "mismatch"])

    spoken = normal[:MAX_ENTRIES_SPOKEN]
    normal_text = " ".join(describe(g) for g in spoken)
    if len(normal) > len(spoken):
        normal_text += f" There were {len(normal) - len(spoken)} more after that."

    mismatch_text = " ".join(describe(g, also=bool(normal_text) or i > 0) for i, g in enumerate(mismatches))
    return normal_text, mismatch_text


def rephrase(draft: str, entries: list[dict]) -> str:
    if not draft:
        return draft
    facts = [{"time": e["time"], "channel": e["channel"], "name": e["name"], "heard": e["heard"],
              "assistant_said": spoken_core(e["earshot_said"]), "message_left": e["message_left"]} for e in entries]
    reply = llm.complete(REPHRASE_PROMPT, f"Activity log: {json.dumps(facts)}\n\nDraft: {draft}", max_tokens=400)
    if not reply:
        return draft
    reply = reply.strip().strip('"').strip()
    if not reply or len(reply) > MAX_REPHRASE_GROWTH * len(draft) + 40:
        return draft
    return reply


def summarise(entries: list[dict], use_llm: bool = True) -> str:
    normal_text, mismatch_text = template_summary(entries)
    if use_llm:
        normal_text = rephrase(normal_text, [e for e in entries if e["verification"] != "mismatch"])
    return " ".join(t for t in (normal_text, mismatch_text) if t)


def deliver_digest(path: Path = ACTIVITY_FILE, use_llm: bool = True) -> tuple[str, list[str]] | None:
    entries = undelivered(load_activity(path))
    if not entries:
        return None
    text = summarise(entries, use_llm)
    ids = [e["id"] for e in entries]
    mark_delivered(ids, path)
    return text, ids
