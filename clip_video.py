#!/usr/bin/env python3
"""YouTube Video Clip Generator — Extract viral TikTok clips from YouTube finance videos."""

import argparse
import os
import re
import sys
import uuid
import yaml
from pathlib import Path

from clipper.download import download_video, download_from_oci
from clipper.transcript import get_transcript, format_transcript_for_ai
from clipper.analyze import analyze_transcript_ollama, analyze_transcript_anthropic, analyze_transcript_oci, rewrite_clip_titles_oci
from clipper.facedetect import detect_face, detect_face_in_clip
from clipper.captions import generate_captions_file
from clipper.transcribe_clip import transcribe_clip_words
from clipper.render import render_clip, detect_silence_boundaries


def extract_video_id(url_or_id: str) -> str:
    """Extract YouTube video ID from URL or return as-is if already an ID."""
    patterns = [
        r'(?:v=|\/v\/|youtu\.be\/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return url_or_id


def load_config(config_path: str = "config.yaml") -> dict:
    if not os.path.exists(config_path):
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def main():
    parser = argparse.ArgumentParser(description="Generate TikTok clips from YouTube finance videos")
    parser.add_argument("url", help="YouTube video URL or ID")
    parser.add_argument("--title", "-t", help="Video title (auto-fetched if not provided)")
    parser.add_argument("--config", "-c", default="config.yaml", help="Config file path")
    parser.add_argument("--ai", default="oci", choices=["ollama", "anthropic", "oci"],
                        help="AI backend for analysis (default: oci)")
    parser.add_argument("--ollama-host", default="http://localhost:11434", help="Ollama host URL")
    parser.add_argument("--ollama-model", default="llama3.1:8b", help="Ollama model name")
    parser.add_argument("--anthropic-key", help="Anthropic API key (or set ANTHROPIC_API_KEY env)")
    parser.add_argument("--skip-download", action="store_true", help="Skip download (use cached)")
    parser.add_argument("--cookies", default="", help="Path to YouTube cookies.txt file")
    parser.add_argument("--skip-face", action="store_true", help="Skip face detection")
    parser.add_argument("--no-captions", action="store_true", help="Disable caption generation")
    parser.add_argument("--no-title", action="store_true", help="Disable hook title banner")
    parser.add_argument("--max-clips", type=int, default=5, help="Maximum clips to generate")
    parser.add_argument("--quality", "-q", default="final", choices=["draft", "final"],
                        help="Quality preset: draft (fast preview, no face/vosk) or final (full quality)")
    args = parser.parse_args()

    config = load_config(args.config)
    project_dir = Path(__file__).parent.resolve()
    data_dir = str(project_dir / "data")
    output_dir = str(project_dir / "output" / "clips")

    video_id = extract_video_id(args.url)
    print(f"Video ID: {video_id}")

    # --- Stage 1: Download ---
    print("=" * 50)
    print("STAGE 1: Downloading video...")
    cookies_file = args.cookies or str(Path(data_dir) / "cookies.txt")
    video_path = str(Path(data_dir) / "videos" / f"{video_id}.mp4")
    if args.skip_download and os.path.exists(video_path):
        print(f"  Using cached: {video_path}")
    else:
        # Try OCI Object Storage first, then yt-dlp
        try:
            video_path = download_from_oci(video_id, str(Path(data_dir) / "videos"))
        except Exception:
            print("  Not found in OCI storage, trying yt-dlp...")
            video_path = download_video(video_id, str(Path(data_dir) / "videos"), cookies_file=cookies_file)
        print(f"  → {video_path}")

    # --- Stage 2: Transcript ---
    print("=" * 50)
    print("STAGE 2: Extracting transcript...")
    try:
        segments = get_transcript(video_id, cookies_file=cookies_file)
    except RuntimeError:
        # No YouTube transcript — fall back to Vosk transcription
        print("  No online transcript, transcribing with Vosk...")
        import json
        from clipper.transcribe_clip import transcribe_clip
        import subprocess as _sp
        _probe = _sp.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True,
        )
        _duration = float(_probe.stdout.strip())
        segments = transcribe_clip(video_path, 0, _duration)
        # Cache for reuse
        transcript_cache = str(Path(data_dir) / "videos" / f"{video_id}_transcript.json")
        with open(transcript_cache, "w") as f:
            json.dump(segments, f)
        print(f"  Vosk: {len(segments)} segments (saved to cache)")
    transcript = format_transcript_for_ai(segments)
    print(f"  → {len(segments)} segments, {len(transcript)} characters")

    # --- Stage 3: AI Analysis ---
    print("=" * 50)
    print("STAGE 3: Analyzing transcript for viral moments...")
    video_title = args.title or f"YouTube video {video_id}"

    # Context limits per AI backend
    context_limits = {
        "oci": 200000,      # Gemini 2.5 Flash — 1M tokens (~4M chars), 200K is safe
        "anthropic": 100000, # Claude — 200K tokens
        "ollama": 25000,     # Local models �� limited context
    }
    max_chars = context_limits.get(args.ai, 25000)

    if len(transcript) > max_chars:
        print(f"  Truncating transcript from {len(transcript)} to {max_chars} chars for AI analysis")
        transcript = transcript[:max_chars]
    else:
        print(f"  Using full transcript ({len(transcript)} chars)")

    if args.ai == "ollama":
        clips = analyze_transcript_ollama(
            video_title, transcript,
            host=args.ollama_host, model=args.ollama_model,
        )
    elif args.ai == "oci":
        clips = analyze_transcript_oci(
            video_title, transcript,
            model_id="google.gemini-2.5-flash",
        )
        # Fallback: if Gemini returns too few clips, retry with Grok
        if len(clips) < args.max_clips:
            print(f"  Gemini returned {len(clips)} clips, retrying with Grok for better coverage...")
            grok_transcript = transcript[:25000] if len(transcript) > 25000 else transcript
            grok_clips = analyze_transcript_oci(
                video_title, grok_transcript,
                model_id="xai.grok-3-mini-fast",
            )
            # Merge: keep unique clips by checking for time overlap
            for gc in grok_clips:
                overlaps = any(
                    abs(gc["startTime"] - c["startTime"]) < 15 for c in clips
                )
                if not overlaps:
                    clips.append(gc)
            clips = sorted(clips, key=lambda c: c["score"], reverse=True)
    else:
        api_key = (args.anthropic_key
                   or os.environ.get("ANTHROPIC_API_KEY")
                   or config.get("api_keys", {}).get("anthropic", ""))
        if not api_key:
            print("  Error: No Anthropic API key. Set --anthropic-key, ANTHROPIC_API_KEY env, or add to config.yaml")
            sys.exit(1)
        clips = analyze_transcript_anthropic(video_title, transcript, api_key)

    clips = clips[:args.max_clips]
    print(f"  → Found {len(clips)} clips:")
    for i, clip in enumerate(clips):
        print(f"    {i+1}. [{clip['startTime']:.0f}s-{clip['endTime']:.0f}s] "
              f"Score: {clip['score']} — {clip['title']}")
        if clip.get("description"):
            print(f"       📝 {clip['description']}")

    # Two-pass: rewrite titles using actual clip transcript content
    if args.ai == "oci":
        print("\n  Rewriting titles with two-pass AI...")
        clips = rewrite_clip_titles_oci(clips, segments)
        for i, clip in enumerate(clips):
            print(f"    {i+1}. {clip['title']}")

    is_draft = args.quality == "draft"
    if is_draft:
        print("\n  ⚡ Draft mode: skipping face detection and Vosk word-level timing")

    # --- Stage 4 + 5: Prepare + render clips (parallel) ---
    print("=" * 50)
    print("STAGE 4-5: Preparing & rendering clips...")
    captions_dir = str(Path(data_dir) / "captions")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Prepare all clips first (captions, face detection) — sequential due to vosk model
    clip_jobs = []
    for i, clip in enumerate(clips):
        clip_id = str(uuid.uuid4())[:8]
        print(f"\n  Preparing clip {i+1}/{len(clips)}: {clip['title']}")
        print(f"    Time: {clip['startTime']:.0f}s - {clip['endTime']:.0f}s "
              f"({clip['endTime'] - clip['startTime']:.0f}s)")

        # Auto-trim leading/trailing silence
        trimmed_start, trimmed_end = detect_silence_boundaries(
            video_path, clip["startTime"], clip["endTime"]
        )
        if trimmed_start != clip["startTime"] or trimmed_end != clip["endTime"]:
            print(f"    Auto-trimmed: {trimmed_start:.1f}s - {trimmed_end:.1f}s "
                  f"({trimmed_end - trimmed_start:.1f}s)")
            clip["startTime"] = trimmed_start
            clip["endTime"] = trimmed_end

        # Per-clip face detection (skip in draft mode)
        if args.skip_face or is_draft:
            face_pos = {"found": False}
        else:
            print("    Detecting face...")
            face_pos = detect_face_in_clip(video_path, clip["startTime"], clip["endTime"])

        # Captions — use Vosk word-level timing in final mode, even split in draft
        captions_path = None
        if not args.no_captions:
            print("    Generating captions...")
            vosk_words = None
            if not is_draft:
                vosk_words = transcribe_clip_words(video_path, clip["startTime"], clip["endTime"])
                if vosk_words:
                    print(f"    → Vosk: {len(vosk_words)} words with precise timing")
            captions_path = generate_captions_file(
                clip_id, segments, clip["startTime"], clip["endTime"], captions_dir,
                vosk_words=vosk_words,
            )

        output_path = str(Path(output_dir) / f"{clip_id}_{i+1}.mp4")
        clip_jobs.append({
            "input_path": video_path,
            "output_path": output_path,
            "start_time": clip["startTime"],
            "end_time": clip["endTime"],
            "captions_file": captions_path,
            "clip_title": None if args.no_title else clip["title"],
            "face_position": face_pos,
            "draft": is_draft,
        })

    # Render all clips in parallel
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from platform_utils import get_thread_count
    max_threads = min(get_thread_count(), len(clip_jobs))
    print(f"\n  Rendering {len(clip_jobs)} clips in parallel ({max_threads} threads)...")

    def _render_one(job):
        render_clip(**job)
        return job["output_path"]

    output_paths = []
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {executor.submit(_render_one, job): i for i, job in enumerate(clip_jobs)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                path = future.result()
                file_size = os.path.getsize(path) / (1024 * 1024)
                print(f"    ✓ Clip {idx+1} → {path} ({file_size:.1f} MB)")
                output_paths.append(path)
            except Exception as e:
                print(f"    ✗ Clip {idx+1} failed: {e}")

    output_paths.sort()  # Sort by filename for consistent ordering

    # Save descriptions alongside clips
    descriptions = {}
    for i, clip in enumerate(clips):
        desc = clip.get("description", "")
        if desc:
            descriptions[f"clip_{i+1}"] = {
                "title": clip["title"],
                "description": desc,
                "score": clip["score"],
            }

    if descriptions:
        import json
        desc_path = str(Path(output_dir) / f"{video_id}_descriptions.json")
        with open(desc_path, "w") as f:
            json.dump(descriptions, f, indent=2)

    print("\n" + "=" * 50)
    print(f"Done! Generated {len(output_paths)} clips in {output_dir}/")
    for i, p in enumerate(output_paths):
        print(f"  {p}")
        desc = clips[i].get("description", "") if i < len(clips) else ""
        if desc:
            print(f"    📝 {desc}")

    if descriptions:
        print(f"\n  Descriptions saved to: {desc_path}")


if __name__ == "__main__":
    main()
