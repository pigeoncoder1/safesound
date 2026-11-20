import numpy as np
import torch
from silero_vad import VADIterator, load_silero_vad

from .config import settings
from .speaker import SAMPLE_RATE, identify, load_voices
from .people import load_people
from .stt import transcribe

VAD_WINDOW = 512
MIN_SPEECH_SECONDS = 0.5
MIN_SILENCE_MS = 500
MAX_SEGMENT_SECONDS = 8.0


class Listener:
    def __init__(self, extra_names: list[str] | None = None):
        self.extra_names = list(extra_names or [])
        self.vad = VADIterator(load_silero_vad(), sampling_rate=SAMPLE_RATE, min_silence_duration_ms=MIN_SILENCE_MS)
        self.voices = load_voices()
        self.names = [p["name"] for p in load_people()] + self.extra_names
        self.pending = np.zeros(0, dtype=np.float32)
        self.segment: list[np.ndarray] | None = None
        self.muted = False

    def reload_people(self) -> None:
        self.voices = load_voices()
        self.names = [p["name"] for p in load_people()] + self.extra_names

    def mute(self) -> None:
        self.muted = True
        self.pending = np.zeros(0, dtype=np.float32)
        self.segment = None
        self.vad.reset_states()

    def unmute(self) -> None:
        self.muted = False

    def feed(self, pcm16: bytes) -> list[np.ndarray]:
        if self.muted:
            return []
        samples = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
        self.pending = np.concatenate([self.pending, samples])

        finished = []
        while len(self.pending) >= VAD_WINDOW:
            window, self.pending = self.pending[:VAD_WINDOW], self.pending[VAD_WINDOW:]
            event = self.vad(torch.from_numpy(window.copy()))

            if event and "start" in event and self.segment is None:
                self.segment = []
            if self.segment is not None:
                self.segment.append(window)

            if event and "end" in event and self.segment is not None:
                finished.append(np.concatenate(self.segment))
                self.segment = None
            elif self.segment is not None and len(self.segment) * VAD_WINDOW >= MAX_SEGMENT_SECONDS * SAMPLE_RATE:
                finished.append(np.concatenate(self.segment))
                self.segment = []
        return finished

    def analyse(self, segment: np.ndarray) -> dict | None:
        seconds = round(len(segment) / SAMPLE_RATE, 2)
        if seconds < MIN_SPEECH_SECONDS:
            return None
        label, score = identify(segment, self.voices, settings.match_threshold)
        return {
            "label": label,
            "score": round(score, 3),
            "seconds": seconds,
            "reliable": seconds >= settings.min_chunk_seconds,
        }

    def transcribe(self, segment: np.ndarray) -> str:
        return transcribe(segment, self.names)
