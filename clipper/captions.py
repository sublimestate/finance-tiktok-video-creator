"""Generate ASS subtitle files with karaoke-style captions."""

import re
from pathlib import Path
from typing import List, Dict


def _format_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    s_whole = int(s)
    cs = int((s - s_whole) * 100)
    return f"{h}:{m:02d}:{s_whole:02d}.{cs:02d}"


def build_caption_events(
    segments: List[Dict],
    clip_start: float,
    clip_end: float,
) -> List[Dict]:
    """Build caption events from transcript segments.

    Returns list of {"start": float, "end": float, "words": [str]}.
    """
    events = []
    for seg in segments:
        if seg["start"] < clip_start - 0.5 or seg["start"] >= clip_end:
            continue
        cleaned = re.sub(r'\[.*?\]', '', seg["text"])
        cleaned = re.sub(r'\(.*?\)', '', cleaned).strip()
        if not cleaned:
            continue
        words = cleaned.split()
        if not words:
            continue

        seg_start = max(0, seg["start"] - clip_start)
        seg_end = min(clip_end - clip_start, seg["end"] - clip_start)
        if seg_end <= seg_start:
            continue
        seg_duration = seg_end - seg_start

        # Split into groups of 3-4 words
        words_per_group = 4
        groups = [words[i:i + words_per_group] for i in range(0, len(words), words_per_group)]
        group_duration = seg_duration / len(groups)

        for i, group in enumerate(groups):
            g_start = seg_start + i * group_duration
            g_end = min(seg_start + (i + 1) * group_duration, clip_end - clip_start)
            events.append({"start": g_start, "end": g_end, "words": group})

    # Prevent overlaps — each event must end before the next starts
    for i in range(len(events) - 1):
        if events[i]["end"] > events[i + 1]["start"]:
            events[i]["end"] = events[i + 1]["start"] - 0.05

    # Also ensure no event is too long (max 3 seconds)
    for e in events:
        if e["end"] - e["start"] > 3.0:
            e["end"] = e["start"] + 3.0

    return [e for e in events if e["end"] > e["start"] + 0.1]


def generate_captions_file(
    clip_id: str,
    segments: List[Dict],
    clip_start: float,
    clip_end: float,
    output_dir: str,
) -> str:
    """Generate an ASS subtitle file with karaoke-style captions.

    Returns the path to the generated ASS file.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = str(Path(output_dir) / f"{clip_id}.ass")

    caption_events = build_caption_events(segments, clip_start, clip_end)

    header = """[Script Info]
Title: Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,80,&H0000D4AA,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,0,2,40,40,320,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    event_lines = []
    for ev in caption_events:
        start = _format_ass_time(ev["start"])
        end = _format_ass_time(ev["end"])
        duration = ev["end"] - ev["start"]
        word_duration_cs = max(1, round((duration / len(ev["words"])) * 100))
        karaoke_text = " ".join(
            f"{{\\kf{word_duration_cs}}}{word.upper()}" for word in ev["words"]
        )
        event_lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{karaoke_text}")

    with open(output_path, "w") as f:
        f.write(header + "\n" + "\n".join(event_lines) + "\n")

    return output_path
