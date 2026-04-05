#!/usr/bin/env python3
"""Search Rumble for finance videos on a topic and generate TikTok clips."""

import argparse
import os
import re
import subprocess
import sys
import yaml
import requests
from pathlib import Path
from typing import List, Dict


def load_config(config_path: str = "config.yaml") -> dict:
    if not os.path.exists(config_path):
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def search_rumble_videos(topic: str, serpapi_key: str, max_results: int = 5) -> List[Dict]:
    """Search for Rumble videos on a topic using SerpAPI."""
    resp = requests.get("https://serpapi.com/search.json", params={
        "q": f"site:rumble.com {topic}",
        "api_key": serpapi_key,
        "num": max_results * 2,  # fetch extra to filter
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    videos = []
    for result in data.get("organic_results", []):
        url = result.get("link", "")
        # Only keep actual video pages (not channels/about pages)
        if re.match(r'https://rumble\.com/v[a-zA-Z0-9]+-.*\.html', url):
            videos.append({
                "title": result.get("title", ""),
                "url": url,
                "snippet": result.get("snippet", ""),
            })
        if len(videos) >= max_results:
            break

    return videos


def get_video_metadata(url: str) -> Dict:
    """Get video metadata from Rumble using yt-dlp."""
    yt_dlp = str(Path(__file__).resolve().parent / "yt-dlp")
    result = subprocess.run(
        [yt_dlp, "--impersonate", "chrome", "--print",
         "%(title)s|||%(duration)s|||%(id)s", "--simulate", url],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return {}

    parts = result.stdout.strip().split("|||")
    if len(parts) >= 3:
        return {
            "title": parts[0],
            "duration": int(float(parts[1])),
            "id": parts[2],
        }
    return {}


def download_rumble_video(url: str, output_dir: str, video_id: str) -> str:
    """Download a Rumble video using yt-dlp with impersonation."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = str(Path(output_dir) / f"{video_id}.mp4")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        print(f"  Using cached: {output_path}")
        return output_path

    yt_dlp = str(Path(__file__).resolve().parent / "yt-dlp")
    result = subprocess.run(
        [yt_dlp, "--impersonate", "chrome",
         "-f", "best[ext=mp4]/best",
         "-o", output_path, url],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to download: {result.stderr[-300:]}")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Search Rumble for finance videos and generate TikTok clips"
    )
    parser.add_argument("topic", help="Topic to search for (e.g. 'stock market crash 2026')")
    parser.add_argument("--max-videos", type=int, default=1,
                        help="Number of videos to process (default: 1)")
    parser.add_argument("--max-clips", type=int, default=5,
                        help="Max clips per video (default: 5)")
    parser.add_argument("--quality", "-q", default="final", choices=["draft", "final"],
                        help="Quality preset")
    parser.add_argument("--min-duration", type=int, default=120,
                        help="Minimum video duration in seconds (default: 120)")
    parser.add_argument("--config", "-c", default="config.yaml", help="Config file path")
    args = parser.parse_args()

    config = load_config(args.config)
    serpapi_key = config.get("api_keys", {}).get("serpapi_key", "")
    if not serpapi_key:
        print("Error: No SerpAPI key in config.yaml")
        sys.exit(1)

    project_dir = Path(__file__).parent.resolve()
    data_dir = str(project_dir / "data")
    videos_dir = str(Path(data_dir) / "videos")

    # --- Stage 1: Search ---
    print("=" * 50)
    print(f"STAGE 1: Searching Rumble for '{args.topic}'...")
    search_results = search_rumble_videos(args.topic, serpapi_key, max_results=args.max_videos * 3)
    print(f"  Found {len(search_results)} video results")

    # --- Stage 2: Filter & select videos ---
    selected = []
    for result in search_results:
        if len(selected) >= args.max_videos:
            break
        print(f"\n  Checking: {result['title']}")
        meta = get_video_metadata(result["url"])
        if not meta:
            print("    ✗ Could not get metadata, skipping")
            continue
        if meta["duration"] < args.min_duration:
            print(f"    ✗ Too short ({meta['duration']}s < {args.min_duration}s)")
            continue
        print(f"    ✓ {meta['title']} ({meta['duration'] // 60}m {meta['duration'] % 60}s)")
        result.update(meta)
        selected.append(result)

    if not selected:
        print("\nNo suitable videos found. Try a different topic or lower --min-duration.")
        sys.exit(1)

    print(f"\n  Selected {len(selected)} video(s) for clip generation")

    # --- Stage 3: Download & generate clips ---
    for i, video in enumerate(selected):
        print("\n" + "=" * 50)
        print(f"VIDEO {i+1}/{len(selected)}: {video['title']}")
        print("=" * 50)

        # Download
        print("\n  Downloading...")
        try:
            video_path = download_rumble_video(video["url"], videos_dir, video["id"])
            print(f"  → {video_path}")
        except Exception as e:
            print(f"  ✗ Download failed: {e}")
            continue

        # Generate clips using clip_video.py pipeline
        print("\n  Generating clips...")
        cmd = [
            sys.executable, str(project_dir / "clip_video.py"),
            video["id"],
            "--ai", "oci",
            "--skip-download",
            "--max-clips", str(args.max_clips),
            "--quality", args.quality,
            "--title", video["title"],
        ]
        result = subprocess.run(cmd, timeout=900)
        if result.returncode != 0:
            print(f"  ✗ Clip generation failed")

    print("\n" + "=" * 50)
    print("Done!")


if __name__ == "__main__":
    main()
