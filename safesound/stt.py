from pathlib import Path

import numpy as np

from .config import settings

MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models" / "whisper"
NO_SPEECH_CUTOFF = 0.6

_model = None


def load_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8", download_root=str(MODEL_DIR))
    return _model


def transcribe(audio: np.ndarray) -> str:
    segments, _ = load_model().transcribe(
        audio.astype(np.float32),
        language="en",
        beam_size=1,
        condition_on_previous_text=False,
        vad_filter=False,
    )
    words = [s.text.strip() for s in segments if s.no_speech_prob < NO_SPEECH_CUTOFF]
    return " ".join(w for w in words if w).strip()
