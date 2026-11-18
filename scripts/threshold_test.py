import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safesound.config import settings
from safesound.speaker import SAMPLE_RATE, embed, load_wav, similarity

ROOT = Path(__file__).resolve().parent.parent
CLIP_LENGTHS = [1.0, 1.5, 2.0, 3.0]
SILENCE_RMS = 0.01
MAX_TRIES = 50


def load_folder(folder: Path) -> list[tuple[str, np.ndarray]]:
    files = sorted(folder.glob("*.wav"))
    if not files:
        sys.exit(f"No .wav files found in {folder}")
    return [(f.name, load_wav(f)) for f in files]


def random_clips(audio: np.ndarray, seconds: float, count: int, rng: np.random.Generator) -> list[np.ndarray]:
    size = int(seconds * SAMPLE_RATE)
    if len(audio) < size:
        return []
    clips = []
    for _ in range(count * MAX_TRIES):
        start = rng.integers(0, len(audio) - size + 1)
        clip = audio[start:start + size]
        if np.sqrt(np.mean(clip ** 2)) >= SILENCE_RMS:
            clips.append(clip)
            if len(clips) == count:
                break
    return clips


def score_files(files, voiceprint, seconds, count, rng) -> np.ndarray:
    scores = []
    for name, audio in files:
        clips = random_clips(audio, seconds, count, rng)
        if len(clips) < count:
            print(f"  note: {name} gave only {len(clips)} usable {seconds}s clips")
        scores += [similarity(voiceprint, embed(c)) for c in clips]
    return np.array(scores)


def accuracy(owner: np.ndarray, other: np.ndarray, threshold: float) -> float:
    correct = np.sum(owner >= threshold) + np.sum(other < threshold)
    return float(correct / (len(owner) + len(other)))


def best_threshold(owner: np.ndarray, other: np.ndarray) -> tuple[float, float]:
    points = np.unique(np.concatenate([owner, other]))
    candidates = np.concatenate([[points[0] - 1e-3], (points[:-1] + points[1:]) / 2, [points[-1] + 1e-3]])
    accs = [accuracy(owner, other, t) for t in candidates]
    i = int(np.argmax(accs))
    return float(candidates[i]), accs[i]


def save_histogram(owner, other, threshold, seconds, out_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bins = np.linspace(min(owner.min(), other.min()), max(owner.max(), other.max()), 30)
    ax.hist(owner, bins=bins, alpha=0.6, label=f"owner (n={len(owner)})")
    ax.hist(other, bins=bins, alpha=0.6, label=f"other (n={len(other)})")
    ax.axvline(threshold, color="black", linestyle="--", label=f"best threshold {threshold:.3f}")
    ax.axvline(settings.match_threshold, color="red", linestyle=":", label=f"config threshold {settings.match_threshold}")
    ax.set_title(f"Similarity to owner voiceprint, {seconds}s clips")
    ax.set_xlabel("cosine similarity")
    ax.set_ylabel("clips")
    ax.legend(loc="upper center")
    fig.tight_layout()
    path = out_dir / f"hist_{seconds:.1f}s.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Find the speaker-match threshold that best separates owner from others.")
    parser.add_argument("--test-dir", type=Path, default=ROOT / "data" / "test")
    parser.add_argument("--voice", type=Path, default=ROOT / "data" / "voices" / "owner.npy")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "results")
    parser.add_argument("--clips-per-file", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    voiceprint = np.load(args.voice)
    owner_files = load_folder(args.test_dir / "owner")
    other_files = load_folder(args.test_dir / "other")
    print(f"{len(owner_files)} owner files, {len(other_files)} other files, {args.clips_per_file} clips per file\n")

    args.out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    summary = []

    for seconds in CLIP_LENGTHS:
        print(f"=== {seconds}s clips ===")
        owner = score_files(owner_files, voiceprint, seconds, args.clips_per_file, rng)
        other = score_files(other_files, voiceprint, seconds, args.clips_per_file, rng)
        if len(owner) == 0 or len(other) == 0:
            print("  not enough audio for this clip length, skipping\n")
            continue

        print(f"  {'':6} {'n':>4} {'mean':>7} {'min':>7} {'max':>7}")
        for label, s in (("owner", owner), ("other", other)):
            print(f"  {label:6} {len(s):>4} {s.mean():>7.3f} {s.min():>7.3f} {s.max():>7.3f}")

        threshold, acc = best_threshold(owner, other)
        config_acc = accuracy(owner, other, settings.match_threshold)
        print(f"  best threshold {threshold:.3f} -> accuracy {acc:.1%}")
        print(f"  config threshold {settings.match_threshold} -> accuracy {config_acc:.1%}")
        print(f"  histogram: {save_histogram(owner, other, threshold, seconds, args.out)}\n")
        summary.append((seconds, threshold, acc, config_acc))

    if summary:
        print("=== summary ===")
        print(f"  {'clip':>5} {'best thr':>9} {'acc':>7} {'acc @ config':>13}")
        for seconds, threshold, acc, config_acc in summary:
            print(f"  {seconds:>4}s {threshold:>9.3f} {acc:>7.1%} {config_acc:>13.1%}")


if __name__ == "__main__":
    main()
