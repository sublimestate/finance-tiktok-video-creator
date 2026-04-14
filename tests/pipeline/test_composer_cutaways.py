"""Tests for pipeline/composer.py cutaway_overrides extension.

Verifies that when a scene's index is in cutaway_overrides, build_background
uses the provided mp4 as the source for that scene's segment instead of
running the normal stock-asset path.
"""
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from pipeline import composer
from pipeline.parser import Scene, Visuals


def _make_scene(idx: int, asset: str = "/fake/pexels.mp4") -> Scene:
    s = Scene()
    s.index = idx
    s.audio_duration = 3.0
    s.duration = 3.0
    s.visuals = Visuals(type="news_video", query="test")
    s.asset_path = asset
    return s


def test_build_background_uses_cutaway_override_for_marked_scenes(tmp_path: Path):
    """When scene index 1 is in cutaway_overrides, ffmpeg is invoked with
    the override mp4 as input, not the scene's asset_path."""
    scenes = [_make_scene(0), _make_scene(1), _make_scene(2)]
    cutaway = tmp_path / "cutaway.mp4"
    cutaway.write_bytes(b"\x00\x00\x00 ftypisom" + b"x" * 100)

    captured_cmds = []

    def fake_run(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        # Simulate ffmpeg writing an output file so the concat step doesn't fail
        if "-i" in cmd:
            try:
                output = cmd[-1]
                if isinstance(output, str) and output.endswith(".mp4"):
                    Path(output).parent.mkdir(parents=True, exist_ok=True)
                    Path(output).write_bytes(b"\x00\x00\x00 ftypisom" + b"x" * 50)
            except Exception:
                pass
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        return result

    with patch.object(composer.subprocess, "run", side_effect=fake_run):
        composer.build_background(
            scenes,
            tmp_dir=str(tmp_path),
            cutaway_overrides={1: str(cutaway)},
        )

    # Find the per-scene render commands (those with -t <duration> and a per-scene seg path)
    per_scene_cmds = [c for c in captured_cmds if any("scene_" in str(arg) for arg in c)]
    assert len(per_scene_cmds) == 3, f"expected 3 per-scene renders, got {len(per_scene_cmds)}"

    # The middle scene (index 1) must use the cutaway mp4 as its input,
    # not the asset_path
    middle_cmd = next(c for c in per_scene_cmds if "scene_001" in " ".join(map(str, c)))
    assert str(cutaway) in middle_cmd, "scene 1 should use cutaway path as -i input"
    assert "/fake/pexels.mp4" not in " ".join(map(str, middle_cmd))

    # The other scenes should still use their asset_path
    first_cmd = next(c for c in per_scene_cmds if "scene_000" in " ".join(map(str, c)))
    assert "/fake/pexels.mp4" in first_cmd


def test_build_background_without_overrides_unchanged_behavior(tmp_path: Path):
    """When cutaway_overrides is None or empty, build_background uses the
    normal stock-asset path for every scene."""
    scenes = [_make_scene(0), _make_scene(1)]
    captured_cmds = []

    def fake_run(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        if "-i" in cmd:
            try:
                output = cmd[-1]
                if isinstance(output, str) and output.endswith(".mp4"):
                    Path(output).parent.mkdir(parents=True, exist_ok=True)
                    Path(output).write_bytes(b"x" * 50)
            except Exception:
                pass
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        return result

    with patch.object(composer.subprocess, "run", side_effect=fake_run):
        composer.build_background(scenes, tmp_dir=str(tmp_path))

    # Both scenes should reference the asset_path
    per_scene_cmds = [c for c in captured_cmds if any("scene_" in str(arg) for arg in c)]
    assert len(per_scene_cmds) == 2
    for cmd in per_scene_cmds:
        assert "/fake/pexels.mp4" in cmd, "no override → should use asset_path"
