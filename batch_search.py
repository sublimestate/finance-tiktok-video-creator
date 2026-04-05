#!/usr/bin/env python3
"""Parallel Rumble batch search + clip generation.

Searches Rumble for multiple topics, filters videos by duration,
downloads and transcribes in parallel, generates clips, and cleans up.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import yaml
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Optional

PROJECT_DIR = Path(__file__).resolve().parent
YT_DLP = str(PROJECT_DIR / "yt-dlp")


def load_config(config_path: str = "config.yaml") -> dict:
    if not os.path.exists(config_path):
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def search_rumble(topic: str, serpapi_key: str, max_results: int = 3) -> List[Dict]:
    """Search Rumble for videos on a topic via SerpAPI."""
    try:
        resp = requests.get("https://serpapi.com/search.json", params={
            "q": f"site:rumble.com {topic}",
            "api_key": serpapi_key,
            "num": max_results * 3,
        }, timeout=15)
        data = resp.json()
        videos = []
        for r in data.get("organic_results", []):
            url = r.get("link", "")
            if re.match(r'https://rumble\.com/v[a-zA-Z0-9]+-.*\.html', url):
                videos.append({
                    "topic": topic,
                    "title": r.get("title", ""),
                    "url": url,
                })
            if len(videos) >= max_results:
                break
        return videos
    except Exception as e:
        print(f"  Search error [{topic}]: {e}")
        return []


def get_metadata(video: Dict) -> Optional[Dict]:
    """Get video metadata using yt-dlp."""
    try:
        result = subprocess.run(
            [YT_DLP, "--impersonate", "chrome", "--print",
             "%(title)s|||%(duration)s|||%(id)s", "--simulate", video["url"]],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        parts = result.stdout.strip().split("|||")
        if len(parts) >= 3:
            video["duration"] = int(float(parts[1]))
            video["id"] = parts[2]
            video["real_title"] = parts[0]
            return video
    except Exception:
        pass
    return None


def download_video(video: Dict, videos_dir: str) -> Optional[str]:
    """Download a Rumble video."""
    output_path = str(Path(videos_dir) / f"{video['id']}.mp4")
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return output_path
    try:
        result = subprocess.run(
            [YT_DLP, "--impersonate", "chrome", "-f", "best[ext=mp4]/best",
             "-o", output_path, video["url"]],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
    except Exception:
        pass
    return None


def transcribe_video(video: Dict, video_path: str) -> bool:
    """Transcribe a video with Vosk (small model, fast)."""
    cache_path = str(Path(video_path).parent / f"{video['id']}_transcript.json")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        return True
    try:
        from clipper.transcribe_clip import transcribe_clip
        segments = transcribe_clip(video_path, 0, video["duration"])
        with open(cache_path, "w") as f:
            json.dump(segments, f)
        return len(segments) > 0
    except Exception as e:
        print(f"  Transcription error [{video['id']}]: {e}")
        return False


def generate_clips(video: Dict, max_clips: int, quality: str) -> List[Dict]:
    """Run clip_video.py for a video."""
    cmd = [
        sys.executable, str(PROJECT_DIR / "clip_video.py"),
        video["id"],
        "--ai", "oci",
        "--skip-download",
        "--max-clips", str(max_clips),
        "--quality", quality,
        "--title", video["real_title"],
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            print(f"  Clip gen failed [{video['id']}]:\n{result.stderr[-300:]}")
            return []

        # Load generated descriptions
        desc_path = PROJECT_DIR / "output" / "clips" / f"{video['id']}_descriptions.json"
        if desc_path.exists():
            with open(desc_path) as f:
                return list(json.load(f).values())
    except Exception as e:
        print(f"  Clip gen exception [{video['id']}]: {e}")
    return []


def main():
    parser = argparse.ArgumentParser(description="Batch Rumble search + clip generation")
    parser.add_argument("topics", nargs="+", help="Topics to search for")
    parser.add_argument("--clips-per-video", type=int, default=2)
    parser.add_argument("--videos-per-topic", type=int, default=1)
    parser.add_argument("--quality", default="draft", choices=["draft", "final"])
    parser.add_argument("--min-duration", type=int, default=300,
                        help="Min video duration in seconds (default: 300 / 5 min)")
    parser.add_argument("--max-duration", type=int, default=1800,
                        help="Max video duration in seconds (default: 1800 / 30 min)")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--cleanup", action="store_true",
                        help="Delete cached videos after clip generation")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    serpapi_key = config.get("api_keys", {}).get("serpapi_key", "")
    if not serpapi_key:
        print("Error: No SerpAPI key in config.yaml")
        sys.exit(1)

    videos_dir = str(PROJECT_DIR / "data" / "videos")
    Path(videos_dir).mkdir(parents=True, exist_ok=True)

    t0 = time.time()

    # --- Stage 1: Search all topics (serial, fast) ---
    print("=" * 50)
    print(f"STAGE 1: Searching Rumble for {len(args.topics)} topics...")
    all_videos = []
    for topic in args.topics:
        results = search_rumble(topic, serpapi_key, max_results=args.videos_per_topic * 2)
        all_videos.extend(results)
    print(f"  Found {len(all_videos)} candidate videos")

    # --- Stage 2: Get metadata in parallel + filter ---
    print("\n" + "=" * 50)
    print(f"STAGE 2: Fetching metadata (parallel, {args.max_workers} workers)...")
    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        results = list(pool.map(get_metadata, all_videos))

    # Filter by duration, dedupe by video id, keep best per topic
    valid = []
    seen_ids = set()
    topics_covered = {}
    for v in results:
        if not v:
            continue
        if v["id"] in seen_ids:
            continue
        if v["duration"] < args.min_duration or v["duration"] > args.max_duration:
            continue
        topic_count = topics_covered.get(v["topic"], 0)
        if topic_count >= args.videos_per_topic:
            continue
        topics_covered[v["topic"]] = topic_count + 1
        seen_ids.add(v["id"])
        valid.append(v)
        print(f"  ✓ [{v['topic']}] {v['real_title'][:60]} ({v['duration']//60}m{v['duration']%60}s)")

    if not valid:
        print("\nNo suitable videos found.")
        sys.exit(1)

    print(f"\n  Processing {len(valid)} videos")

    # --- Stage 3: Parallel download + transcribe (pipelined) ---
    print("\n" + "=" * 50)
    print(f"STAGE 3: Downloading + transcribing (parallel, {args.max_workers} workers)...")

    def download_and_transcribe(v):
        path = download_video(v, videos_dir)
        if not path:
            return (v, None, False)
        print(f"  ⬇ Downloaded: {v['id']} ({os.path.getsize(path) // (1024*1024)}MB)")
        ok = transcribe_video(v, path)
        if ok:
            print(f"  ✎ Transcribed: {v['id']}")
        return (v, path, ok)

    ready_videos = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        futures = [pool.submit(download_and_transcribe, v) for v in valid]
        for future in as_completed(futures):
            v, path, ok = future.result()
            if path and ok:
                ready_videos.append((v, path))

    print(f"\n  {len(ready_videos)}/{len(valid)} videos ready for clip generation")

    # --- Stage 4: Generate clips (serial — clip_video.py does its own parallelism) ---
    print("\n" + "=" * 50)
    print(f"STAGE 4: Generating clips from {len(ready_videos)} videos...")
    all_clips = []
    for v, path in ready_videos:
        print(f"\n  → [{v['topic']}] {v['real_title'][:60]}")
        clips = generate_clips(v, args.clips_per_video, args.quality)
        for clip in clips:
            clip["topic"] = v["topic"]
            clip["source_video"] = v["real_title"]
        all_clips.extend(clips)
        print(f"    Generated {len(clips)} clips")

    # Sort by score
    all_clips.sort(key=lambda c: c.get("score", 0), reverse=True)

    # --- Stage 5: Optional cleanup ---
    if args.cleanup:
        print("\n" + "=" * 50)
        print("STAGE 5: Cleaning up cached videos...")
        freed = 0
        for v, path in ready_videos:
            if os.path.exists(path):
                freed += os.path.getsize(path)
                os.unlink(path)
        print(f"  Freed {freed // (1024*1024)}MB")

    # --- Summary ---
    elapsed = time.time() - t0
    print("\n" + "=" * 50)
    print(f"Done in {elapsed:.0f}s. Top {min(10, len(all_clips))} clips by virality:\n")
    for i, clip in enumerate(all_clips[:10]):
        print(f"{i+1}. [{clip.get('topic', '?')}] Score: {clip.get('score', '?')}")
        print(f"   {clip['title']}")
        print(f"   📝 {clip.get('description', '')}")
        print()

    # Save batch summary
    summary_path = PROJECT_DIR / "output" / "clips" / "batch_summary.json"
    with open(summary_path, "w") as f:
        json.dump({
            "elapsed_seconds": elapsed,
            "videos_processed": len(ready_videos),
            "total_clips": len(all_clips),
            "top_clips": all_clips[:10],
        }, f, indent=2)
    print(f"  Summary saved to: {summary_path}")


if __name__ == "__main__":
    main()
