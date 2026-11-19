import re
from pathlib import Path

import numpy as np

from .commands import relationship_in
from .people import PEOPLE_FILE, upsert_person
from .speaker import CHUNK_SECONDS, SAMPLE_RATE, VOICES_DIR, voiceprint_from

TARGET_SECONDS = 15.0
MIN_SECONDS = 6.0
TIMEOUT_SECONDS = 30.0
MAX_ASKS = 2
RESERVED_LABELS = {"owner", "unknown"}
CANCEL = re.compile(r"\b(?:cancel|never\s?mind|forget it|don't worry|stop)\b", re.I)

ASK_RELATIONSHIP = "Is {name} a friend or family?"
ASK_AGAIN = "Sorry, is {name} a friend or family?"
ASK_TO_SPEAK = "Hi {name}, could you say a few sentences so I'll recognise you next time?"
REMEMBERED = "Got it, I'll remember you, {name}."
NOT_ENOUGH = "Sorry {name}, I didn't catch enough to remember you. We can try again later."
CANCELLED = "No problem, we can do that another time."
ALREADY_OWNER = "I already know you, {name}."
NO_NAME = "Sorry, I didn't catch their name."


def voice_label(name: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", name.lower())


def problem_with(name: str | None, owner: str | None) -> str | None:
    if not name or not voice_label(name):
        return NO_NAME
    if owner and name.lower() == owner.lower():
        return ALREADY_OWNER.format(name=owner)
    if voice_label(name) in RESERVED_LABELS:
        return NO_NAME
    return None


class Introduction:
    def __init__(self, name: str, relationship: str | None, now: float,
                 people_file: Path = PEOPLE_FILE, voices_dir: Path = VOICES_DIR):
        self.name = name
        self.label = voice_label(name)
        self.relationship = relationship if relationship in ("partner", "friend") else None
        self.stage = "collecting" if self.relationship else "asking"
        self.deadline = now + TIMEOUT_SECONDS
        self.asks = 0 if self.relationship else 1
        self.audio: list[np.ndarray] = []
        self.people_file = people_file
        self.voices_dir = voices_dir

    def opening_line(self) -> str:
        if self.stage == "asking":
            return ASK_RELATIONSHIP.format(name=self.name)
        return ASK_TO_SPEAK.format(name=self.name)

    def hear_answer(self, text: str, now: float) -> str:
        if CANCEL.search(text or ""):
            self.stage = "cancelled"
            return CANCELLED
        relationship = relationship_in(text)
        if relationship:
            self.relationship = relationship
            self.stage = "collecting"
            self.deadline = now + TIMEOUT_SECONDS
            return ASK_TO_SPEAK.format(name=self.name)
        if self.asks >= MAX_ASKS:
            self.stage = "cancelled"
            return CANCELLED
        self.asks += 1
        self.deadline = now + TIMEOUT_SECONDS
        return ASK_AGAIN.format(name=self.name)

    def wants(self, label: str) -> bool:
        return self.stage == "collecting" and label in ("unknown", self.label)

    def add(self, segment: np.ndarray) -> bool:
        self.audio.append(segment)
        return self.collected_seconds >= TARGET_SECONDS

    @property
    def collected_seconds(self) -> float:
        return sum(len(a) for a in self.audio) / SAMPLE_RATE

    def timed_out(self, now: float) -> bool:
        return self.stage in ("asking", "collecting") and now >= self.deadline

    def cancel(self) -> str:
        self.stage = "cancelled"
        return CANCELLED

    def finish(self) -> str:
        if self.collected_seconds < MIN_SECONDS:
            self.stage = "failed"
            return NOT_ENOUGH.format(name=self.name)
        voiceprint, used, _ = voiceprint_from(np.concatenate(self.audio))
        if voiceprint is None or used * CHUNK_SECONDS < MIN_SECONDS:
            self.stage = "failed"
            return NOT_ENOUGH.format(name=self.name)

        self.voices_dir.mkdir(parents=True, exist_ok=True)
        np.save(self.voices_dir / f"{self.label}.npy", voiceprint)
        upsert_person(self.name, self.relationship, f"voices/{self.label}.npy", self.people_file)
        self.stage = "done"
        return REMEMBERED.format(name=self.name)

    def status(self) -> dict:
        return {
            "type": "introduction",
            "name": self.name,
            "relationship": self.relationship,
            "stage": self.stage,
            "seconds": round(self.collected_seconds, 1),
            "target": TARGET_SECONDS,
        }
