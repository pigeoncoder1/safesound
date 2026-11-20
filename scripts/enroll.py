import argparse
import sys
import textwrap
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safesound.owner_setup import ENROL_PROMPT
from safesound.speaker import SAMPLE_RATE, VOICES_DIR, load_wav, voiceprint_from

ROOT = Path(__file__).resolve().parent.parent
ENROLL_DIR = ROOT / "data" / "enroll"

PROMPT = textwrap.fill(ENROL_PROMPT, width=72)


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

    voiceprint, used, total = voiceprint_from(audio)
    print(f"Used {used} of {total} chunks ({total - used} too quiet).")

    if voiceprint is None:
        print("No usable speech found. Check your microphone and try again.")
        sys.exit(1)

    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    npy_path = VOICES_DIR / f"{args.name}.npy"
    np.save(npy_path, voiceprint)
    print(f"Saved voiceprint to {npy_path}")


if __name__ == "__main__":
    main()
