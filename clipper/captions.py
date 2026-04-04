"""Generate ASS subtitle files with karaoke-style captions and pop animation."""

import re
from pathlib import Path
from typing import List, Dict, Optional


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


def build_caption_events_wordlevel(
    vosk_words: List[Dict],
    clip_duration: float,
) -> List[Dict]:
    """Build caption events from Vosk word-level timestamps.

    vosk_words: list of {"word": str, "start": float, "end": float} (0-based)
    Returns list of {"start": float, "end": float, "word_timings": [{"word": str, "duration_cs": int}]}
    """
    if not vosk_words:
        return []

    events = []
    words_per_group = 4

    for i in range(0, len(vosk_words), words_per_group):
        group = vosk_words[i:i + words_per_group]
        if not group:
            continue
        g_start = group[0]["start"]
        g_end = group[-1]["end"]
        if g_end > clip_duration:
            g_end = clip_duration

        word_timings = []
        for w in group:
            dur_cs = max(1, round((w["end"] - w["start"]) * 100))
            word_timings.append({"word": w["word"], "duration_cs": dur_cs})

        events.append({
            "start": g_start,
            "end": g_end,
            "word_timings": word_timings,
        })

    # Prevent overlaps
    for i in range(len(events) - 1):
        if events[i]["end"] > events[i + 1]["start"]:
            events[i]["end"] = events[i + 1]["start"] - 0.05

    # Max 3 seconds
    for e in events:
        if e["end"] - e["start"] > 3.0:
            e["end"] = e["start"] + 3.0

    return [e for e in events if e["end"] > e["start"] + 0.1]


def _build_karaoke_text_wordlevel(word_timings: List[Dict]) -> str:
    """Build ASS karaoke text with per-word timing and border pop animation."""
    parts = []
    for wt in word_timings:
        dur_cs = wt["duration_cs"]
        word = wt["word"].upper()
        # Pop animation: border pulses thicker then settles (no vertical shift)
        pop = (
            f"{{\\kf{dur_cs}"
            f"\\t(0,80,\\bord8)"
            f"\\t(80,200,\\bord5)}}"
        )
        parts.append(f"{pop}{word}")
    return " ".join(parts)


def _build_karaoke_text_even(words: List[str], duration: float) -> str:
    """Build ASS karaoke text with even timing and border pop animation (fallback)."""
    word_duration_cs = max(1, round((duration / len(words)) * 100))
    parts = []
    for word in words:
        pop = (
            f"{{\\kf{word_duration_cs}"
            f"\\t(0,80,\\bord8)"
            f"\\t(80,200,\\bord5)}}"
        )
        parts.append(f"{pop}{word.upper()}")
    return " ".join(parts)


def generate_captions_file(
    clip_id: str,
    segments: List[Dict],
    clip_start: float,
    clip_end: float,
    output_dir: str,
    vosk_words: Optional[List[Dict]] = None,
) -> str:
    """Generate an ASS subtitle file with karaoke-style captions and pop animation.

    If vosk_words is provided, uses accurate per-word timing.
    Otherwise falls back to even timing from transcript segments.

    Returns the path to the generated ASS file.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = str(Path(output_dir) / f"{clip_id}.ass")

    header = """[Script Info]
Title: Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,80,&H00FFFFFF,&H0000FF00,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,40,40,500,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    event_lines = []

    if vosk_words:
        # Word-level timing from Vosk
        clip_duration = clip_end - clip_start
        events = build_caption_events_wordlevel(vosk_words, clip_duration)
        for ev in events:
            start = _format_ass_time(ev["start"])
            end = _format_ass_time(ev["end"])
            karaoke_text = _build_karaoke_text_wordlevel(ev["word_timings"])
            event_lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{karaoke_text}")
    else:
        # Fallback: even timing from transcript segments
        caption_events = build_caption_events(segments, clip_start, clip_end)
        for ev in caption_events:
            start = _format_ass_time(ev["start"])
            end = _format_ass_time(ev["end"])
            duration = ev["end"] - ev["start"]
            karaoke_text = _build_karaoke_text_even(ev["words"], duration)
            event_lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{karaoke_text}")

    with open(output_path, "w") as f:
        f.write(header + "\n" + "\n".join(event_lines) + "\n")

    return output_path
