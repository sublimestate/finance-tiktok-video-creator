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
from clipper.analyze import analyze_transcript_ollama, analyze_transcript_anthropic, analyze_transcript_oci
from clipper.facedetect import detect_face, detect_face_in_clip
from clipper.captions import generate_captions_file
from clipper.transcribe_clip import transcribe_clip
from clipper.render import render_clip


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
    segments = get_transcript(video_id, cookies_file=cookies_file)
    transcript = format_transcript_for_ai(segments)
    print(f"  → {len(segments)} segments, {len(transcript)} characters")

    # --- Stage 3: AI Analysis ---
    print("=" * 50)
    print("STAGE 3: Analyzing transcript for viral moments...")
    video_title = args.title or f"YouTube video {video_id}"

    # Truncate transcript if too long (LLMs have context limits)
    if len(transcript) > 25000:
        print(f"  Truncating transcript from {len(transcript)} to 25000 chars for AI analysis")
        transcript = transcript[:25000]

    if args.ai == "ollama":
        clips = analyze_transcript_ollama(
            video_title, transcript,
            host=args.ollama_host, model=args.ollama_model,
        )
    elif args.ai == "oci":
        clips = analyze_transcript_oci(
            video_title, transcript,
            model_id="xai.grok-3-mini-fast",
        )
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

    # --- Stage 4 + 5: Per-clip face detection + render ---
    print("=" * 50)
    print("STAGE 4-5: Detecting faces & rendering clips...")
    captions_dir = str(Path(data_dir) / "captions")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    output_paths = []
    for i, clip in enumerate(clips):
        clip_id = str(uuid.uuid4())[:8]
        print(f"\n  Clip {i+1}/{len(clips)}: {clip['title']}")
        print(f"    Time: {clip['startTime']:.0f}s - {clip['endTime']:.0f}s "
              f"({clip['endTime'] - clip['startTime']:.0f}s)")

        # Per-clip face detection
        if args.skip_face:
            face_pos = {"found": False}
        else:
            print("    Detecting face in clip...")
            face_pos = detect_face_in_clip(video_path, clip["startTime"], clip["endTime"])
            if face_pos["found"]:
                print(f"    Face at ({face_pos['x']}, {face_pos['y']})")
            else:
                print("    No face, using blurred fallback")

        # Captions
        captions_path = None
        if not args.no_captions:
            print("    Transcribing clip for captions...")
            clip_segments = transcribe_clip(video_path, clip["startTime"], clip["endTime"])
            if clip_segments:
                adjusted_segments = [
                    {"start": s["start"] + clip["startTime"],
                     "end": s["end"] + clip["startTime"],
                     "text": s["text"]}
                    for s in clip_segments
                ]
                print(f"    Transcribed {len(clip_segments)} segments")
            else:
                adjusted_segments = segments
                print("    Using full video transcript (fallback)")

            print("    Generating captions...")
            captions_path = generate_captions_file(
                clip_id, adjusted_segments, clip["startTime"], clip["endTime"], captions_dir
            )

        # Render
        print("    Rendering...")
        output_path = str(Path(output_dir) / f"{clip_id}_{i+1}.mp4")
        render_clip(
            input_path=video_path,
            output_path=output_path,
            start_time=clip["startTime"],
            end_time=clip["endTime"],
            captions_file=captions_path,
            clip_title=None if args.no_title else clip["title"],
            face_position=face_pos,
        )
        file_size = os.path.getsize(output_path) / (1024 * 1024)
        print(f"    → {output_path} ({file_size:.1f} MB)")
        output_paths.append(output_path)

    print("\n" + "=" * 50)
    print(f"Done! Generated {len(output_paths)} clips in {output_dir}/")
    for p in output_paths:
        print(f"  {p}")


if __name__ == "__main__":
    main()
