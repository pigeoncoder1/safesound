from .config import settings

UNKNOWN = "unknown"
OWNER = "owner"


class RoomState:
    def __init__(self, cooldown_seconds: float | None = None, unknown_chunks_to_flip: int | None = None):
        self.cooldown = settings.room_cooldown_seconds if cooldown_seconds is None else cooldown_seconds
        self.flip_after = settings.unknown_chunks_to_flip if unknown_chunks_to_flip is None else unknown_chunks_to_flip
        self.last_heard: dict[str, float] = {}
        self.unknown_streak = 0
        self.last_confirmed_unknown: float | None = None

    def observe(self, label: str, now: float) -> None:
        self.last_heard[label] = now
        if label == UNKNOWN:
            self.unknown_streak += 1
            if self.unknown_streak >= self.flip_after:
                self.last_confirmed_unknown = now
        else:
            self.unknown_streak = 0

    def state(self, now: float) -> str:
        if self.last_confirmed_unknown is not None and now - self.last_confirmed_unknown < self.cooldown:
            return "not_private"
        return "private"

    def owner_last_heard(self, now: float) -> float | None:
        if OWNER not in self.last_heard:
            return None
        return now - self.last_heard[OWNER]

    def voices_present(self, now: float) -> list[dict]:
        present = [
            {"label": label, "last_heard_seconds_ago": round(now - heard, 1)}
            for label, heard in self.last_heard.items()
            if now - heard < self.cooldown
        ]
        return sorted(present, key=lambda v: v["last_heard_seconds_ago"])

    def snapshot(self, now: float) -> dict:
        owner = self.owner_last_heard(now)
        return {
            "type": "room",
            "state": self.state(now),
            "owner_last_heard": None if owner is None else round(owner, 1),
            "voices": self.voices_present(now),
        }

    def change_key(self, now: float) -> tuple:
        return self.state(now), tuple(v["label"] for v in self.voices_present(now))
