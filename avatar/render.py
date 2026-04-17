"""High-level avatar cutaway renderer.

Calls EchoMimic V1 via Modal for GPU inference, with a fail-soft
fallback to a still-portrait video if Modal is unavailable or the
render errors. The video always ships.
"""
import os
import subprocess
from pathlib import Path
from typing import List, Tuple

MODAL_APP_NAME = os.environ.get("MODAL_APP_NAME", "echomimic-v1")
MODAL_FUNCTION_NAME = os.environ.get("MODAL_FUNCTION_NAME", "render")


def _probe_duration(audio_path: Path) -> str:
    """Return the audio duration as a string (seconds) via ffprobe."""
    proc = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(audio_path),
        ],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"ffprobe failed on {audio_path}: {proc.stderr[:200]}")
    return proc.stdout.strip()


def render_still_portrait_fallback(
    portrait_path: Path, audio_path: Path, output_path: Path
) -> Path:
    """Build a 1080x1920 video showing the portrait centered with the audio.

    Used when Modal is unavailable, render times out, or the EchoMimic
    output is unusable. The video still ships — just without animation.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = _probe_duration(audio_path)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", duration, "-i", str(portrait_path),
        "-i", str(audio_path),
        "-filter_complex",
        "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black[bg]",
        "-map", "[bg]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"fallback ffmpeg failed: {result.stderr[-300:]}")
    return output_path


def _modal_render(portrait_path: Path, audio_path: Path, output_path: Path) -> Path:
    """Call EchoMimic via the deployed Modal function.

    Reads portrait + audio as bytes, sends to Modal, writes the returned
    mp4 bytes to output_path. Modal handles GPU provisioning, scaling,
    and teardown — no RunPod lifecycle code needed.
    """
    import modal

    render_fn = modal.Function.from_name(MODAL_APP_NAME, MODAL_FUNCTION_NAME)
    portrait_bytes = portrait_path.read_bytes()
    audio_bytes = audio_path.read_bytes()
    result_bytes = render_fn.remote(portrait_bytes, audio_bytes)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(result_bytes)
    return output_path


def render_cutaway(
    portrait_path: Path,
    audio_path: Path,
    output_path: Path,
) -> Path:
    """Render one talking-head cutaway. Prefers Modal, falls back to still portrait.

    Returns the output path on success (Modal or fallback). Raises if both
    paths fail (e.g., disk full during fallback ffmpeg).
    """
    try:
        return _modal_render(portrait_path, audio_path, output_path)
    except Exception as exc:
        print(f"  ⚠ avatar render failed ({type(exc).__name__}): {exc}; falling back to still portrait")
        return render_still_portrait_fallback(portrait_path, audio_path, output_path)


def render_cutaways_batch(
    portrait_path: Path,
    jobs: List[Tuple[Path, Path]],
) -> List[Path]:
    """Render N cutaways via Modal. Each job is (audio, output).

    Each call is independent (Modal handles GPU scaling). Per-job failures
    fall back to still-portrait individually.
    """
    results: List[Path] = []
    for audio, output in jobs:
        try:
            results.append(_modal_render(portrait_path, audio, output))
        except Exception as exc:
            print(f"  ⚠ cutaway {output.name} failed: {exc}; using still fallback")
            results.append(
                render_still_portrait_fallback(portrait_path, audio, output)
            )
    return results
