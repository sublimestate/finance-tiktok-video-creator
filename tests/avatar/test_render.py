"""Tests for avatar/render.py — high-level cutaway renderer with fallback."""
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


def test_render_cutaways_batch_all_fall_back_on_session_failure(
    tmp_path: Path, fake_portrait: Path, fake_audio: Path, monkeypatch
):
    """When RunPodSession fails on __enter__, all N jobs use still-portrait fallback."""
    class BoomSession:
        def __init__(self, *a, **kw): pass
        def __enter__(self): raise RuntimeError("out of stock")
        def __exit__(self, *a): pass
    monkeypatch.setattr(render_module, "RunPodSession", BoomSession)

    jobs = [(fake_audio, tmp_path / f"out{i}.mp4") for i in range(3)]
    results = render_module.render_cutaways_batch(fake_portrait, jobs, "test:image")

    assert len(results) == 3
    for r in results:
        assert r.exists() and r.stat().st_size > 0


def test_render_cutaways_batch_per_job_fallback(
    tmp_path: Path, fake_portrait: Path, fake_audio: Path, monkeypatch
):
    """When mid-batch render fails, only that job falls back; others use RunPod."""
    render_count = [0]

    class PartialSession:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def render(self, portrait, audio, output):
            render_count[0] += 1
            if render_count[0] == 2:  # Fail on second job
                raise RuntimeError("OOM")
            output.write_bytes(b"\x00\x00\x00 ftypisomRUNPOD_MARKER" + b"\x00" * 100)
            return output

    monkeypatch.setattr(render_module, "RunPodSession", PartialSession)
    jobs = [(fake_audio, tmp_path / f"out{i}.mp4") for i in range(3)]
    results = render_module.render_cutaways_batch(fake_portrait, jobs, "test:image")

    assert len(results) == 3
    # Job 1: used RunPod (has marker)
    assert b"RUNPOD_MARKER" in results[0].read_bytes()
    # Job 2: fell back (no marker — fallback writes a real mp4 via ffmpeg)
    assert b"RUNPOD_MARKER" not in results[1].read_bytes()
    assert results[1].exists() and results[1].stat().st_size > 0
    # Job 3: used RunPod (has marker — pod was still alive after job 2's per-job fallback)
    assert b"RUNPOD_MARKER" in results[2].read_bytes()
