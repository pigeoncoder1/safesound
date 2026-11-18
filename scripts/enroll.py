import argparse
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safesound.speaker import SAMPLE_RATE, embed, load_wav

ROOT = Path(__file__).resolve().parent.parent
ENROLL_DIR = ROOT / "data" / "enroll"
VOICES_DIR = ROOT / "data" / "voices"

CHUNK_SECONDS = 2.0
SILENCE_RMS = 0.01

PROMPT = """\
The quick brown fox jumps over the lazy dog, but nobody saw it happen.
On Monday morning I took the early train into the city, bought a coffee
and a warm blueberry muffin, and watched the rain run down the window.
My favourite numbers are seven, nineteen and forty-two. Please remind me
to call the dentist on Thursday, pay the electricity bill, and water the
plants before the weekend. If anyone asks, I'll be back at half past six,
probably tired, hungry, and thinking about what to cook for dinner."""


def record(seconds: float) -> np.ndarray:
    print("\nRead this aloud at a normal pace. Keep going until the timer ends:\n")
    print(PROMPT)
    print()
    for n in (3, 2, 1):
        print(f"Starting in {n}...", end="\r", flush=True)
        time.sleep(1)

    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    start = time.time()
    while (left := seconds - (time.time() - start)) > 0:
        print(f"Recording... {left:4.1f}s left ", end="\r", flush=True)
        time.sleep(0.1)
    sd.wait()
    print("Recording... done.        ")
    return audio[:, 0]


def split_chunks(audio: np.ndarray) -> list[np.ndarray]:
    size = int(CHUNK_SECONDS * SAMPLE_RATE)
    return [audio[i:i + size] for i in range(0, len(audio) - size + 1, size)]


def rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(chunk ** 2)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrol a voice for safesound.")
    parser.add_argument("--name", required=True, help="e.g. owner or trusted")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--from-wav", type=Path, help="use an existing recording instead of the mic")
    args = parser.parse_args()

    if args.from_wav:
        audio = load_wav(args.from_wav)
        print(f"Loaded {args.from_wav} ({len(audio) / SAMPLE_RATE:.1f}s)")
    else:
        audio = record(args.seconds)
        ENROLL_DIR.mkdir(parents=True, exist_ok=True)
        wav_path = ENROLL_DIR / f"{args.name}.wav"
        sf.write(wav_path, audio, SAMPLE_RATE)
        print(f"Saved recording to {wav_path}")

    chunks = split_chunks(audio)
    voiced = [c for c in chunks if rms(c) >= SILENCE_RMS]
    print(f"Used {len(voiced)} of {len(chunks)} chunks ({len(chunks) - len(voiced)} too quiet).")

    if not voiced:
        print("No usable speech found. Check your microphone and try again.")
        sys.exit(1)

    mean = np.mean([embed(c) for c in voiced], axis=0)
    voiceprint = (mean / (np.linalg.norm(mean) + 1e-9)).astype(np.float32)

    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    npy_path = VOICES_DIR / f"{args.name}.npy"
    np.save(npy_path, voiceprint)
    print(f"Saved voiceprint to {npy_path}")


if __name__ == "__main__":
    main()
