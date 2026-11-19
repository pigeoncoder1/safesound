import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CallSession:
    caller_id: str | None
    started_at: float = field(default_factory=time.time)
    voice_labels: list[str] = field(default_factory=list)

    @property
    def latest_voice(self) -> str | None:
        return self.voice_labels[-1] if self.voice_labels else None


_current: CallSession | None = None


def start_call(caller_id: str | None) -> CallSession:
    global _current
    if _current is not None:
        raise RuntimeError("a call is already in progress")
    _current = CallSession(caller_id=caller_id.strip() if caller_id and caller_id.strip() else None)
    return _current


def end_call() -> CallSession | None:
    global _current
    finished, _current = _current, None
    return finished


def current_call() -> CallSession | None:
    return _current


def find_person(name: str, people: list[dict]) -> dict | None:
    return next((p for p in people if p["name"].lower() == name.lower()), None)


def verify_caller(caller_id: str | None, voice_label: str | None, people: list[dict]) -> str:
    if caller_id is None:
        return "unknown_number"
    person = find_person(caller_id, people)
    if person is None:
        return "unknown_number"
    if voice_label is None:
        return "pending"
    if Path(person["voice_file"]).stem == voice_label:
        return "verified"
    return "mismatch"


def effective_relationship(caller_id: str | None, voice_label: str | None, people: list[dict]) -> str:
    if verify_caller(caller_id, voice_label, people) != "verified":
        return "unknown"
    return find_person(caller_id, people)["relationship"]


def call_status(people: list[dict]) -> dict:
    call = current_call()
    if call is None:
        return {"type": "call", "active": False, "caller_id": None, "voice": None, "verification": None}
    return {
        "type": "call",
        "active": True,
        "caller_id": call.caller_id,
        "voice": call.latest_voice,
        "verification": verify_caller(call.caller_id, call.latest_voice, people),
    }
