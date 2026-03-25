"""Render vertical clips with smart cropping, hook titles, and captions."""

import os
import subprocess
from typing import Dict, Optional


def render_clip(
    input_path: str,
    output_path: str,
    start_time: float,
    end_time: float,
    captions_file: Optional[str] = None,
    clip_title: Optional[str] = None,
    face_position: Optional[Dict] = None,
) -> str:
    """Render a vertical 9:16 clip with smart cropping and captions.

    Returns the output file path.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    duration = end_time - start_time

    filters = []

    # Blurred background + centered video (preserves full frame, no cropping)
    filters.append(
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg]"
    )
    filters.append(
        "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg]"
    )
    filters.append("[bg][fg]overlay=(W-w)/2:(H-h)/2[out0]")

    last_label = "out0"

    # Step 2: Hook title banner (first 5 seconds)
    if clip_title:
        escaped = (clip_title
                   .replace("\\", "\\\\")
                   .replace("'", "'\\''")
                   .replace(":", "\\:")
                   .replace(";", "\\;")
                   .replace("%", "%%"))
        filters.append(
            f"[{last_label}]drawbox=x=(iw-800)/2:y=60:w=800:h=120:"
            f"color=white@0.85:t=fill:enable='between(t,0,5)'[out1a]"
        )
        filters.append(
            f"[out1a]drawtext=text='{escaped}':fontsize=42:fontcolor=black:"
            f"x=(w-text_w)/2:y=90:enable='between(t,0,5)'[out1]"
        )
        last_label = "out1"

    # Step 3: Karaoke captions (ASS subtitles)
    if captions_file and os.path.exists(captions_file):
        escaped_path = captions_file.replace("\\", "/").replace(":", "\\:").replace("'", "'\\''")
        filters.append(f"[{last_label}]ass='{escaped_path}'[out2]")
        last_label = "out2"

    # Final null filter
    filters.append(f"[{last_label}]null[out]")
    filter_complex = ";".join(filters)

    # CRITICAL: -ss BEFORE -i resets PTS to 0 (ASS subtitles work correctly)
    cmd = [
        "ffmpeg",
        "-ss", str(start_time),
        "-i", input_path,
        "-t", str(duration),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-y",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg clip render failed: {result.stderr[-500:]}")

    return output_path
