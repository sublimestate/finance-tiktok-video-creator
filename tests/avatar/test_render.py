"""Tests for avatar/render.py — Modal-based cutaway renderer with fallback."""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from avatar import render as render_module
from avatar.render import render_cutaway, render_still_portrait_fallback, render_cutaways_batch


@pytest.fixture
def fake_portrait(tmp_path: Path) -> Path:
    p = tmp_path / "portrait.png"
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
    proc = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(output)],
        capture_output=True, text=True, check=True,
    )
    duration = float(proc.stdout.strip())
    assert 1.5 < duration < 2.5


def test_render_cutaway_falls_back_when_modal_raises(
    tmp_path: Path, fake_portrait: Path, fake_audio: Path, monkeypatch
):
    def boom(*a, **kw):
        raise RuntimeError("Modal unavailable")
    monkeypatch.setattr(render_module, "_modal_render", boom)

    output = tmp_path / "out.mp4"
    result = render_cutaway(
        portrait_path=fake_portrait,
        audio_path=fake_audio,
        output_path=output,
    )
    assert result == output
    assert output.exists() and output.stat().st_size > 0


def test_render_cutaway_uses_modal_when_available(
    tmp_path: Path, fake_portrait: Path, fake_audio: Path, monkeypatch
):
    sentinel = b"\x00\x00\x00 ftypisomMODAL_SENTINEL" + b"\x00" * 100

    def mock_modal_render(portrait, audio, output):
        output.write_bytes(sentinel)
        return output
    monkeypatch.setattr(render_module, "_modal_render", mock_modal_render)

    output = tmp_path / "out.mp4"
    result = render_cutaway(
        portrait_path=fake_portrait,
        audio_path=fake_audio,
        output_path=output,
    )
    assert result == output
    assert output.read_bytes().startswith(b"\x00\x00\x00 ftypisomMODAL_SENTINEL")


def test_render_cutaways_batch_all_fall_back_on_modal_failure(
    tmp_path: Path, fake_portrait: Path, fake_audio: Path, monkeypatch
):
    def boom(*a, **kw):
        raise RuntimeError("Modal unavailable")
    monkeypatch.setattr(render_module, "_modal_render", boom)

    jobs = [(fake_audio, tmp_path / f"out{i}.mp4") for i in range(3)]
    results = render_cutaways_batch(fake_portrait, jobs)

    assert len(results) == 3
    for r in results:
        assert r.exists() and r.stat().st_size > 0


def test_render_cutaways_batch_per_job_fallback(
    tmp_path: Path, fake_portrait: Path, fake_audio: Path, monkeypatch
):
    call_count = [0]

    def partial_modal(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 2:
            raise RuntimeError("OOM")
        portrait, audio, output = args
        output.write_bytes(b"\x00\x00\x00 ftypisomMODAL" + b"\x00" * 100)
        return output

    monkeypatch.setattr(render_module, "_modal_render", partial_modal)
    jobs = [(fake_audio, tmp_path / f"out{i}.mp4") for i in range(3)]
    results = render_cutaways_batch(fake_portrait, jobs)

    assert len(results) == 3
    assert b"MODAL" in results[0].read_bytes()
    assert b"MODAL" not in results[1].read_bytes()
    assert results[1].exists() and results[1].stat().st_size > 0
    assert b"MODAL" in results[2].read_bytes()
