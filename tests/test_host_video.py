"""Tests for host_video.py — orchestration helper functions only.

The full pipeline (research → script → TTS → render) is not unit
tested at the module level. The testable bits are the small helpers
that compute host-beat → audio mappings and cutaway override dicts.
"""
from pathlib import Path

import pytest

from host_video import pair_host_beats_with_audio, build_cutaway_override_map


class _FakeScene:
    def __init__(self, index, audio_path):
        self.index = index
        self.audio_path = audio_path


def test_pair_host_beats_with_audio_picks_only_host_indices(tmp_path: Path):
    """Given a script with mixed host/collage scenes, return only the
    (index, audio_path) pairs for the host scenes."""
    a0 = tmp_path / "s0.wav"; a0.write_bytes(b"a0")
    a1 = tmp_path / "s1.wav"; a1.write_bytes(b"a1")
    a2 = tmp_path / "s2.wav"; a2.write_bytes(b"a2")
    a3 = tmp_path / "s3.wav"; a3.write_bytes(b"a3")
    scenes = [
        _FakeScene(0, str(a0)),
        _FakeScene(1, str(a1)),
        _FakeScene(2, str(a2)),
        _FakeScene(3, str(a3)),
    ]
    host_indices = [1, 3]

    pairs = pair_host_beats_with_audio(scenes, host_indices)

    assert len(pairs) == 2
    assert pairs[0] == (1, Path(str(a1)))
    assert pairs[1] == (3, Path(str(a3)))


def test_pair_returns_empty_when_no_host_beats(tmp_path: Path):
    a0 = tmp_path / "s0.wav"; a0.write_bytes(b"a")
    scenes = [_FakeScene(0, str(a0))]
    assert pair_host_beats_with_audio(scenes, []) == []


def test_build_cutaway_override_map_pairs_indices_with_paths(tmp_path: Path):
    """Given a list of (scene_index, output_path) results from the
    avatar render, return a dict keyed by scene index for build_background."""
    p1 = tmp_path / "cut1.mp4"
    p2 = tmp_path / "cut2.mp4"
    host_indices = [1, 3]
    cutaway_paths = [p1, p2]

    overrides = build_cutaway_override_map(host_indices, cutaway_paths)

    assert overrides == {1: str(p1), 3: str(p2)}


def test_build_cutaway_override_map_raises_on_length_mismatch(tmp_path: Path):
    with pytest.raises(ValueError, match="length mismatch"):
        build_cutaway_override_map([1, 3], [tmp_path / "only_one.mp4"])
