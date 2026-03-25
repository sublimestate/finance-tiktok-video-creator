"""Extract and format YouTube transcripts."""

import json
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Optional


# Ensure Deno is in PATH
_DENO_PATH = os.path.expanduser("~/.deno/bin")
if _DENO_PATH not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _DENO_PATH + ":" + os.environ.get("PATH", "")

# Use local yt-dlp binary if available
_PROJECT_DIR = Path(__file__).parent.parent.resolve()
_LOCAL_YTDLP = str(_PROJECT_DIR / "yt-dlp")
YTDLP_BIN = _LOCAL_YTDLP if os.path.exists(_LOCAL_YTDLP) else "yt-dlp"


def get_transcript(video_id: str, cookies_file: str = "") -> List[Dict]:
    """Fetch transcript segments from YouTube.

    Uses yt-dlp to extract subtitles (works with cookies, bypasses IP blocks).
    Falls back to youtube-transcript-api if yt-dlp fails.

    Returns list of {"start": float, "end": float, "text": str}.
    """
    # Try yt-dlp subtitle extraction first (more reliable with cookies)
    segments = _get_transcript_ytdlp(video_id, cookies_file)
    if segments:
        return segments

    # Fallback to youtube-transcript-api
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from http.cookiejar import MozillaCookieJar

        if cookies_file and Path(cookies_file).exists():
            cookie_jar = MozillaCookieJar(cookies_file)
            cookie_jar.load(ignore_discard=True, ignore_expires=True)
            import requests as _req
            session = _req.Session()
            session.cookies = cookie_jar
            api = YouTubeTranscriptApi(http_client=session)
        else:
            api = YouTubeTranscriptApi()

        items = api.fetch(video_id)
        return [{"start": item.start, "end": item.start + item.duration, "text": item.text}
                for item in items]
    except Exception:
        pass

    # Fallback: check for vosk-generated transcript
    vosk_path = str(Path(os.path.dirname(cookies_file or ".")) / ".." / "videos" / f"{video_id}_transcript.json")
    # Also check in data/videos/
    for candidate in [vosk_path, str(_PROJECT_DIR / "data" / "videos" / f"{video_id}_transcript.json")]:
        if Path(candidate).exists():
            with open(candidate) as f:
                return json.load(f)

    raise RuntimeError(f"Could not fetch transcript for {video_id}")


def _get_transcript_ytdlp(video_id: str, cookies_file: str = "") -> List[Dict]:
    """Extract transcript using yt-dlp subtitle download."""
    import tempfile
    tmp_dir = tempfile.mkdtemp()
    url = f"https://www.youtube.com/watch?v={video_id}"

    cmd = [
        YTDLP_BIN,
        "--write-auto-sub",
        "--sub-lang", "en",
        "--sub-format", "json3",
        "--skip-download",
        "--no-playlist",
        "-o", str(Path(tmp_dir) / "%(id)s"),
    ]
    if cookies_file and Path(cookies_file).exists():
        cmd += ["--cookies", cookies_file]
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    # Look for the subtitle file
    sub_file = None
    for f in Path(tmp_dir).glob(f"{video_id}*.json3"):
        sub_file = str(f)
        break
    if not sub_file:
        for f in Path(tmp_dir).glob(f"{video_id}*.json*"):
            sub_file = str(f)
            break

    if not sub_file:
        return []

    with open(sub_file) as f:
        data = json.load(f)

    segments = []
    for event in data.get("events", []):
        start_ms = event.get("tStartMs", 0)
        dur_ms = event.get("dDurationMs", 0)
        segs = event.get("segs", [])
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if text and text != "\n":
            segments.append({
                "start": start_ms / 1000.0,
                "end": (start_ms + dur_ms) / 1000.0,
                "text": text,
            })

    # Clean up
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return segments


def format_transcript_for_ai(segments: List[Dict]) -> str:
    """Format transcript with timestamps for AI analysis."""
    lines = []
    for s in segments:
        minutes = int(s["start"] // 60)
        seconds = int(s["start"] % 60)
        lines.append(f"[{minutes}:{seconds:02d}] {s['text']}")
    return "\n".join(lines)
