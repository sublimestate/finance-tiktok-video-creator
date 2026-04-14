"""High-level avatar cutaway renderer.

Wraps RunPodSession with a fail-soft fallback: if the GPU path errors
for any reason, produce a still-portrait video with the original audio
so the surrounding pipeline still ships a video.
"""
import subprocess
from pathlib import Path
from typing import List, Tuple

from avatar.runpod import RunPodSession, RunPodError


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

    Used when RunPod is unavailable, render times out, or the LivePortrait
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


def render_cutaway(
    portrait_path: Path,
    audio_path: Path,
    output_path: Path,
    image: str,
) -> Path:
    """Render one talking-head cutaway. Always returns a valid mp4 at output_path.

    Tries RunPod first. On any failure, writes a still-portrait fallback.
    """
    try:
        with RunPodSession(image=image) as pod:
            return pod.render(
                portrait=portrait_path,
                audio=audio_path,
                output=output_path,
            )
    except (RunPodError, Exception) as exc:
        print(f"  ⚠ avatar render failed ({type(exc).__name__}): {exc}; falling back to still portrait")
        return render_still_portrait_fallback(portrait_path, audio_path, output_path)


def render_cutaways_batch(
    portrait_path: Path,
    jobs: List[Tuple[Path, Path]],
    image: str,
) -> List[Path]:
    """Render N cutaways inside one RunPod session. Each job is (audio, output).

    On RunPod failure, ALL jobs fall back to still-portrait individually.
    On a single mid-batch render failure, only that one falls back.
    """
    try:
        with RunPodSession(image=image) as pod:
            results: List[Path] = []
            for audio, output in jobs:
                try:
                    results.append(
                        pod.render(portrait=portrait_path, audio=audio, output=output)
                    )
                except Exception as exc:
                    print(f"  ⚠ cutaway {output.name} failed: {exc}; using still fallback")
                    results.append(
                        render_still_portrait_fallback(portrait_path, audio, output)
                    )
            return results
    except (RunPodError, Exception) as exc:
        print(f"  ⚠ RunPod session failed ({exc}); all cutaways fall back to still portrait")
        return [
            render_still_portrait_fallback(portrait_path, audio, output)
            for audio, output in jobs
        ]
