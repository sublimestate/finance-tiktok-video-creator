"""Render vertical clips with smart cropping, hook titles, and captions."""

import os
import subprocess
from typing import Dict, Optional

from platform_utils import get_video_encode_args


def render_clip(
    input_path: str,
    output_path: str,
    start_time: float,
    end_time: float,
    captions_file: Optional[str] = None,
    clip_title: Optional[str] = None,
    face_position: Optional[Dict] = None,
    draft: bool = False,
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
        def _escape_drawtext(t):
            return (t.replace("\\", "\\\\")
                     .replace("'", "'\\''")
                     .replace(":", "\\:")
                     .replace(";", "\\;")
                     .replace("%", "%%"))

        # Wrap long titles into two lines (~25 chars per line)
        max_chars = 25
        if len(clip_title) > max_chars:
            words = clip_title.split()
            line1, line2 = [], []
            for w in words:
                if len(" ".join(line1 + [w])) <= max_chars:
                    line1.append(w)
                else:
                    line2.append(w)
            lines = [" ".join(line1), " ".join(line2)]
        else:
            lines = [clip_title]

        num_lines = len(lines)
        banner_h = 120 + (num_lines - 1) * 70
        banner_y = 300

        # Dark banner across full width with padding
        filters.append(
            f"[{last_label}]drawbox=x=0:y={banner_y}:w=iw:h={banner_h}:"
            f"color=black@0.7:t=fill:enable='between(t,0,5)'[out1a]"
        )

        # Draw each line of text centered
        prev_label = "out1a"
        for i, line in enumerate(lines):
            escaped = _escape_drawtext(line)
            text_y = banner_y + 25 + i * 70
            next_label = f"out1{'b' if i == 0 and num_lines > 1 else ''}"
            if i == len(lines) - 1:
                next_label = "out1"
            filters.append(
                f"[{prev_label}]drawtext=text='{escaped}':"
                f"fontsize=52:fontcolor=white:borderw=3:bordercolor=black:"
                f"font=Arial:x=(w-text_w)/2:y={text_y}:enable='between(t,0,5)'[{next_label}]"
            )
            prev_label = next_label
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
    ] + get_video_encode_args(crf=32 if draft else 23, preset="ultrafast") + [
        "-c:a", "aac",
        "-b:a", "64k" if draft else "128k",
        "-movflags", "+faststart",
        "-y",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg clip render failed: {result.stderr[-500:]}")

    return output_path
