import numpy as np
import soundfile as sf

from safesound.demo import (
    FRAME_SAMPLES,
    SCENES,
    SPEAKERS,
    TRAILING_SILENCE_SECONDS,
    all_lines,
    call_ends_after,
    lines_needing_llm,
    missing_files,
    pcm_frames,
    playable_scenes,
    readiness_report,
)
from safesound.speaker import SAMPLE_RATE

OWNER = "Richie"


def record_all(folder, skip=()):
    for _, line in all_lines():
        if line.file not in skip:
            sf.write(folder / line.file, np.zeros(1600, dtype=np.float32), SAMPLE_RATE)


def test_script_matches_the_spec():
    assert [s.number for s in SCENES] == [1, 2, 3, 4, 5, 6, 7]
    assert [s.channel for s in SCENES] == ["room", "call", "call", "call", "call", "room", "room"]
    assert [s.caller_id for s in SCENES] == [None, "Reuben", None, "Reuben", "Reuben", None, None]
    assert [s.optional for s in SCENES] == [False, False, False, False, True, False, False]
    files = [line.file for _, line in all_lines()]
    assert len(files) == len(set(files)) == 10
    assert all(line.speaker in SPEAKERS for _, line in all_lines())


def test_owner_name_is_filled_in():
    texts = [line.spoken(OWNER) for _, line in all_lines()]
    assert "Hiya, is Richie about?" in texts
    assert not any("{owner}" in t for t in texts)
    assert SCENES[5].heading(OWNER) == "Richie comes home"


def test_missing_files_split_required_and_optional(tmp_path):
    required, optional = missing_files(tmp_path)
    assert len(required) == 9
    assert optional == ["07_stranger_injection.wav"]
    record_all(tmp_path)
    assert missing_files(tmp_path) == ([], [])


def test_optional_scene_is_skipped_when_not_recorded(tmp_path):
    record_all(tmp_path, skip={"07_stranger_injection.wav"})
    assert [s.number for s in playable_scenes(tmp_path)] == [1, 2, 3, 4, 6, 7]


def test_injection_scene_stays_on_the_same_call(tmp_path):
    record_all(tmp_path)
    scenes = playable_scenes(tmp_path)
    numbers = [s.number for s in scenes]
    assert not call_ends_after(numbers.index(4), scenes)
    assert call_ends_after(numbers.index(5), scenes)
    assert call_ends_after(numbers.index(2), scenes)
    assert not call_ends_after(numbers.index(1), scenes)


def test_call_ends_when_injection_scene_missing(tmp_path):
    record_all(tmp_path, skip={"07_stranger_injection.wav"})
    scenes = playable_scenes(tmp_path)
    assert call_ends_after([s.number for s in scenes].index(4), scenes)


def test_only_the_off_script_lines_need_the_llm():
    needs = lines_needing_llm(OWNER)
    assert [(s.number, line.file) for s, line in needs] == [
        (3, "05_stranger_whereabouts.wav"),
        (5, "07_stranger_injection.wav"),
    ]


def test_pcm_frames_resample_and_add_trailing_silence(tmp_path):
    path = tmp_path / "clip.wav"
    sf.write(path, np.full(44100, 0.5, dtype=np.float32), 44100)
    frames = pcm_frames(path)
    total_samples = int((1.0 + TRAILING_SILENCE_SECONDS) * SAMPLE_RATE)
    assert len(frames) == -(-total_samples // FRAME_SAMPLES)
    assert all(len(f) == FRAME_SAMPLES * 2 for f in frames[:-1])
    assert np.frombuffer(frames[-1], dtype="<i2").max() == 0


def test_readiness_report(tmp_path):
    report = readiness_report(OWNER, llm_on=False, demo_dir=tmp_path)
    assert any("Missing demo recordings" in r for r in report)
    assert any("Optional recordings missing" in r for r in report)
    assert any("scene 3" in r and "whereabouts" in r for r in report)
    record_all(tmp_path)
    assert readiness_report(OWNER, llm_on=True, demo_dir=tmp_path) == []
