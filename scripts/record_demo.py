import argparse
import sys
import time
from pathlib import Path

import sounddevice as sd
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safesound.demo import DEMO_DIR, SPEAKERS, all_lines
from safesound.people import load_people, owner_name
from safesound.speaker import SAMPLE_RATE


def record(seconds: float):
    for n in (3, 2, 1):
        print(f"  Starting in {n}...", end="\r", flush=True)
        time.sleep(1)
    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    start = time.time()
    while (left := seconds - (time.time() - start)) > 0:
        print(f"  Recording... {left:4.1f}s left ", end="\r", flush=True)
        time.sleep(0.1)
    sd.wait()
    print("  Recording... done.        ")
    return audio[:, 0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Record the wav files for python -m safesound.server --demo.")
    parser.add_argument("--speaker", choices=sorted(SPEAKERS), help="only record lines for this speaker")
    parser.add_argument("--only", help="only record this file, e.g. 05_stranger_whereabouts.wav")
    parser.add_argument("--redo", action="store_true", help="re-record files that already exist")
    args = parser.parse_args()

    owner = owner_name(load_people()) or "the owner"
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    for scene, line in all_lines():
        path = DEMO_DIR / line.file
        if args.only and line.file != args.only:
            continue
        if args.speaker and line.speaker != args.speaker:
            continue
        if path.exists() and not args.redo:
            print(f"skip {line.file} (exists; use --redo to replace)")
            continue

        print(f"\n=== {line.file}  (scene {scene.number}: {scene.heading(owner)})")
        print(f"Speaker: {SPEAKERS[line.speaker]}")
        print(f"Say: {line.spoken(owner)}")
        answer = input(f"Press Enter to record {line.seconds:.0f}s, 's' to skip, 'q' to quit: ").strip().lower()
        if answer == "q":
            break
        if answer == "s":
            continue
        sf.write(path, record(line.seconds), SAMPLE_RATE)
        print(f"  Saved {path}")


if __name__ == "__main__":
    main()
