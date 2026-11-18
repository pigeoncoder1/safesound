import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safesound.config import settings
from safesound.speaker import embed, load_wav, similarity


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: python scripts/compare.py first.wav second.wav")
        sys.exit(1)

    path_a, path_b = sys.argv[1], sys.argv[2]
    score = similarity(embed(load_wav(path_a)), embed(load_wav(path_b)))

    verdict = "SAME speaker" if score >= settings.match_threshold else "DIFFERENT speakers"
    print(f"similarity: {score:.3f}  (threshold {settings.match_threshold}) -> {verdict}")


if __name__ == "__main__":
    main()
