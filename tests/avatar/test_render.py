"""Tests for avatar/render.py — high-level cutaway renderer with fallback."""
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from avatar import render as render_module
from avatar.render import render_cutaway, render_still_portrait_fallback


@pytest.fixture
def fake_portrait(tmp_path: Path) -> Path:
    p = tmp_path / "portrait.png"
    # Generate a tiny valid 1x1 PNG via ffmpeg
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1",
         "-frames:v", "1", str(p)],
        capture_output=True, check=True,
    )
    return p


@pytest.fixture
def fake_audio(tmp_path: Path) -> Path:
    a = tmp_path / "audio.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
         "-t", "2", "-c:a", "pcm_s16le", str(a)],
        capture_output=True, check=True,
    )
    return a


def test_still_portrait_fallback_writes_valid_mp4(
    tmp_path: Path, fake_portrait: Path, fake_audio: Path
):
    output = tmp_path / "fallback.mp4"
    result = render_still_portrait_fallback(fake_portrait, fake_audio, output)
    assert result == output
    assert output.exists() and output.stat().st_size > 0
    # Probe duration with ffprobe to confirm it ran
    proc = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(output)],
        capture_output=True, text=True, check=True,
    )
    duration = float(proc.stdout.strip())
    assert 1.5 < duration < 2.5  # ~2 second audio


def test_render_cutaway_falls_back_when_runpod_session_raises(
    tmp_path: Path, fake_portrait: Path, fake_audio: Path, monkeypatch
):
    # Stub RunPodSession to raise on enter
    class BoomSession:
        def __init__(self, *a, **kw): pass
        def __enter__(self): raise RuntimeError("no GPUs available")
        def __exit__(self, *a): pass
    monkeypatch.setattr(render_module, "RunPodSession", BoomSession)

    output = tmp_path / "out.mp4"
    result = render_cutaway(
        portrait_path=fake_portrait,
        audio_path=fake_audio,
        output_path=output,
        image="liveportrait:test",
    )
    assert result == output
    assert output.exists() and output.stat().st_size > 0


def test_render_cutaway_uses_runpod_when_session_works(
    tmp_path: Path, fake_portrait: Path, fake_audio: Path, monkeypatch
):
    # Stub RunPodSession to write a sentinel mp4
    class WorkingSession:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def render(self, portrait, audio, output):
            output.write_bytes(b"\x00\x00\x00 ftypisom" + b"x" * 100)
            return output
    monkeypatch.setattr(render_module, "RunPodSession", WorkingSession)

    output = tmp_path / "out.mp4"
    result = render_cutaway(
        portrait_path=fake_portrait,
        audio_path=fake_audio,
        output_path=output,
        image="liveportrait:test",
    )
    assert result == output
    # Sentinel proves we went through the RunPod path, not the fallback
    assert output.read_bytes().startswith(b"\x00\x00\x00 ftypisom")
