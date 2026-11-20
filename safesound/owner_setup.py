import re
from pathlib import Path

import numpy as np
import soundfile as sf

from .people import PEOPLE_FILE, load_people, save_people
from .speaker import CHUNK_SECONDS, SAMPLE_RATE, VOICES_DIR, voiceprint_from

ENROLL_DIR = Path(__file__).resolve().parent.parent / "data" / "enroll"
OWNER_LABEL = "owner"
TARGET_SECONDS = 30.0
MIN_VOICED_SECONDS = 12.0
PROGRESS_EVERY_SECONDS = 0.5
NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z' -]{0,29}")

ENROL_PROMPT = (
    "The quick brown fox jumps over the lazy dog, but nobody saw it happen. "
    "On Monday morning I took the early train into the city, bought a coffee and a warm blueberry muffin, "
    "and watched the rain run down the window. My favourite numbers are seven, nineteen and forty-two. "
    "Please remind me to call the dentist on Thursday, pay the electricity bill, and water the plants before "
    "the weekend. If anyone asks, I'll be back at half past six, probably tired, hungry, and thinking about "
    "what to cook for dinner."
)


def owner_enrolled(voices_dir: Path = VOICES_DIR, people_file: Path = PEOPLE_FILE) -> bool:
    has_owner = any(p["relationship"] == "owner" for p in load_people(people_file))
    return has_owner and (voices_dir / f"{OWNER_LABEL}.npy").exists()


def clean_name(name) -> str | None:
    if not isinstance(name, str):
        return None
    name = " ".join(name.split())
    return name if NAME_PATTERN.fullmatch(name) else None


def set_owner(name: str, people_file: Path = PEOPLE_FILE) -> list[dict]:
    voice_file = f"voices/{OWNER_LABEL}.npy"
    people = [p for p in load_people(people_file)
              if p["relationship"] != "owner" and p["voice_file"] != voice_file and p["name"].lower() != name.lower()]
    people.insert(0, {"name": name, "relationship": "owner", "voice_file": voice_file})
    save_people(people, people_file)
    return people


class OwnerSetup:
    def __init__(self, name: str, voices_dir: Path = VOICES_DIR, people_file: Path = PEOPLE_FILE,
                 enroll_dir: Path = ENROLL_DIR):
        self.name = name
        self.chunks: list[np.ndarray] = []
        self.samples = 0
        self.reported_at = 0.0
        self.stage = "recording"
        self.voices_dir = voices_dir
        self.people_file = people_file
        self.enroll_dir = enroll_dir

    @property
    def seconds(self) -> float:
        return self.samples / SAMPLE_RATE

    def add(self, pcm16: bytes) -> bool:
        samples = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
        self.chunks.append(samples)
        self.samples += len(samples)
        return self.seconds >= TARGET_SECONDS

    def progress_due(self) -> bool:
        if self.seconds - self.reported_at >= PROGRESS_EVERY_SECONDS:
            self.reported_at = self.seconds
            return True
        return False

    def finish(self) -> str:
        audio = np.concatenate(self.chunks) if self.chunks else np.zeros(0, dtype=np.float32)
        voiceprint, used, _ = voiceprint_from(audio)
        if voiceprint is None or used * CHUNK_SECONDS < MIN_VOICED_SECONDS:
            self.stage = "failed"
            return "I couldn't hear enough speech. Move closer to the microphone and try again."

        self.enroll_dir.mkdir(parents=True, exist_ok=True)
        sf.write(self.enroll_dir / f"{OWNER_LABEL}.wav", audio, SAMPLE_RATE)
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        np.save(self.voices_dir / f"{OWNER_LABEL}.npy", voiceprint)
        set_owner(self.name, self.people_file)
        self.stage = "done"
        return f"All set, {self.name}. I'll recognise your voice from now on."

    def status(self, message: str | None = None) -> dict:
        return {
            "type": "owner_setup",
            "stage": self.stage,
            "name": self.name,
            "seconds": round(self.seconds, 1),
            "target": TARGET_SECONDS,
            "message": message,
        }
