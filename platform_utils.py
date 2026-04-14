"""Platform detection and FFmpeg encoding settings."""

import platform
import subprocess
from typing import List


def is_mac() -> bool:
    return platform.system() == "Darwin"


def has_videotoolbox() -> bool:
    """Check if FFmpeg has VideoToolbox encoder available (macOS)."""
    if not is_mac():
        return False
    try:
        result = subprocess.run(
            ["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=10
        )
        return "h264_videotoolbox" in result.stdout
    except Exception:
        return False


# Cache the result at module load
_USE_VIDEOTOOLBOX = has_videotoolbox()


def get_video_encode_args(crf: int = 23, preset: str = "ultrafast") -> List[str]:
    """Return FFmpeg video encoding arguments for the current platform.

    macOS with VideoToolbox: hardware-accelerated H.264
    Linux/other: software libx264
    """
    if _USE_VIDEOTOOLBOX:
        # VideoToolbox uses -q:v (1-100, lower = better) instead of CRF
        # Map CRF roughly: crf 20 -> q 55, crf 23 -> q 65
        quality = min(100, max(1, 40 + crf))
        return ["-c:v", "h264_videotoolbox", "-q:v", str(quality)]
    else:
        return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]


def get_video_encode_args_simple() -> List[str]:
    """Return minimal video encoding args (for intermediate clips that don't need quality tuning)."""
    if _USE_VIDEOTOOLBOX:
        return ["-c:v", "h264_videotoolbox", "-q:v", "65"]
    else:
        return ["-c:v", "libx264", "-pix_fmt", "yuv420p"]


def get_thread_count() -> int:
    """Return optimal parallel render thread count based on available CPUs."""
    import os
    cpus = os.cpu_count() or 4
    if is_mac():
        return min(cpus, 6)
    # Linux: each FFmpeg libx264 encode is multi-threaded, so cap parallel
    # workers to avoid oversubscribing cores. 12 saturates a 32-vCPU box.
    return max(3, min(cpus - 2, 12))
