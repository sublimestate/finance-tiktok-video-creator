"""Render vertical clips with smart cropping, hook titles, and captions."""

import os
import subprocess
from typing import Dict, Optional, Tuple

from platform_utils import get_video_encode_args


def detect_silence_boundaries(
    input_path: str, start_time: float, end_time: float,
    silence_thresh: int = -35, min_silence_dur: float = 0.5,
) -> Tuple[float, float]:
    """Detect leading/trailing silence and return trimmed start/end times."""
    duration = end_time - start_time
    try:
        result = subprocess.run(
            ["ffmpeg", "-ss", str(start_time), "-i", input_path,
             "-t", str(duration), "-af",
             f"silencedetect=noise={silence_thresh}dB:d={min_silence_dur}",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
        stderr = result.stderr

        # Parse silence periods
        import re
        starts = re.findall(r'silence_start: ([\d.]+)', stderr)
        ends = re.findall(r'silence_end: ([\d.]+)', stderr)

        # Trim leading silence (if silence starts at 0)
        trimmed_start = start_time
        if starts and float(starts[0]) < 0.3:
            if ends:
                trimmed_start = start_time + float(ends[0])

        # Trim trailing silence (if silence extends to the end)
        trimmed_end = end_time
        if starts:
            last_silence_start = float(starts[-1])
            if last_silence_start > duration - 2.0:
                trimmed_end = start_time + last_silence_start + 0.2

        # Safety: don't trim too aggressively
        if trimmed_end - trimmed_start < duration * 0.5:
            return start_time, end_time

        return trimmed_start, trimmed_end

    except Exception:
        return start_time, end_time


def render_clip(
    input_path: str,
    output_path: str,
    start_time: float,
    end_time: float,
    captions_file: Optional[str] = None,
    clip_title: Optional[str] = None,
    hook_quote: Optional[str] = None,
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

    # Step 2: Hook quote overlay (first 2 seconds — scroll-stopping text)
    hook_text = hook_quote or clip_title
    if hook_text:
        def _escape_drawtext(t):
            return (t.replace("\\", "\\\\")
                     .replace("'", "'\\''")
                     .replace(":", "\\:")
                     .replace(";", "\\;")
                     .replace("%", "%%"))

        # Wrap into lines (~20 chars per line for large font)
        max_chars = 20
        words = hook_text.upper().split()
        lines = []
        current_line = []
        for w in words:
            if len(" ".join(current_line + [w])) <= max_chars:
                current_line.append(w)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [w]
        if current_line:
            lines.append(" ".join(current_line))
        lines = lines[:3]  # max 3 lines

        num_lines = len(lines)
        line_height = 80
        banner_h = 40 + num_lines * line_height
        banner_y = int(1920 * 0.15)  # top area of screen

        # Dark semi-transparent background — centered on screen
        filters.append(
            f"[{last_label}]drawbox=x=0:y={banner_y - 20}:w=iw:h={banner_h + 40}:"
            f"color=black@0.75:t=fill:enable='between(t,0,2)'[out1a]"
        )

        # Draw each line of text centered — big bold white
        prev_label = "out1a"
        for i, line in enumerate(lines):
            escaped = _escape_drawtext(line)
            text_y = banner_y + i * line_height + 10
            next_label = f"out1{'b' if i < num_lines - 1 else ''}"
            if i == num_lines - 1:
                next_label = "out1"
            filters.append(
                f"[{prev_label}]drawtext=text='{escaped}':"
                f"fontsize=64:fontcolor=white:borderw=4:bordercolor=black:"
                f"font=Arial:x=(w-text_w)/2:y={text_y}:enable='between(t,0,2)'[{next_label}]"
            )
            prev_label = next_label
        last_label = "out1"

    # Step 3: Karaoke captions (ASS subtitles)
    if captions_file and os.path.exists(captions_file):
        escaped_path = captions_file.replace("\\", "/").replace(":", "\\:").replace("'", "'\\''")
        filters.append(f"[{last_label}]ass='{escaped_path}'[out2]")
        last_label = "out2"

    # Fade in/out (0.3s each)
    fade_in = 0.3
    fade_out = 0.3
    fade_out_start = max(0, duration - fade_out)
    filters.append(
        f"[{last_label}]fade=t=in:st=0:d={fade_in},"
        f"fade=t=out:st={fade_out_start}:d={fade_out}[out]"
    )
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
        "-af", f"afade=t=in:st=0:d={fade_in},afade=t=out:st={fade_out_start}:d={fade_out}",
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
