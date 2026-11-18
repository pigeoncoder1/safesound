from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torchaudio.functional as AF

SAMPLE_RATE = 16_000
EMBEDDING_DIM = 192

MODEL_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models"

_model = None


def load_model():
    global _model
    if _model is None:
        from speechbrain.inference.speaker import EncoderClassifier
        from speechbrain.utils.fetching import LocalStrategy

        _model = EncoderClassifier.from_hparams(
            source=MODEL_SOURCE,
            savedir=str(MODEL_DIR),
            local_strategy=LocalStrategy.COPY,
            run_opts={"device": "cpu"},
        )
        _model.eval()
    return _model


def embed(audio: np.ndarray) -> np.ndarray:
    if audio.ndim != 1:
        raise ValueError(f"expected mono 1-D audio, got shape {audio.shape}")

    model = load_model()
    wav = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32)).unsqueeze(0)

    with torch.inference_mode():
        emb = model.encode_batch(wav)

    vec = emb.squeeze().cpu().numpy().astype(np.float32)

    return vec / (np.linalg.norm(vec) + 1e-9)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def load_wav(path: str | Path) -> np.ndarray:
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)

    if sr != SAMPLE_RATE:
        mono = AF.resample(torch.from_numpy(mono), orig_freq=sr, new_freq=SAMPLE_RATE).numpy()

    return mono.astype(np.float32)
