#!/usr/bin/env python3
"""Finance TikTok Video Creator - Main CLI entry point."""

import argparse
import os
import sys
import time
import yaml
from pathlib import Path
from slugify import slugify

from pipeline.parser import parse_script
from pipeline.tts import generate_tts
from pipeline.assets import fetch_asset
from pipeline.remotion_bridge import render_overlays
from pipeline.composer import build_background, build_audio, compose_final


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    if not os.path.exists(config_path):
        print(f"Error: Config file not found: {config_path}")
        print("Copy config.yaml.example to config.yaml and fill in your API keys.")
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Create finance TikTok videos from scripts")
    parser.add_argument("script", help="Path to YAML script file")
    parser.add_argument("--output", "-o", help="Output filename (default: auto from title)")
    parser.add_argument("--config", "-c", default="config.yaml", help="Config file path")
    parser.add_argument("--skip-assets", action="store_true", help="Skip asset fetching (reuse cached)")
    parser.add_argument("--skip-tts", action="store_true", help="Skip TTS generation (reuse cached)")
    parser.add_argument("--skip-remotion", action="store_true", help="Skip Remotion rendering (reuse cached)")
    args = parser.parse_args()

    config = load_config(args.config)
    api_keys = config.get("api_keys", {})
    output_cfg = config.get("output", {})
    tts_cfg = config.get("tts", {})
    assets_cfg = config.get("assets", {})
    remotion_cfg = config.get("remotion", {})

    width = output_cfg.get("width", 1080)
    height = output_cfg.get("height", 1920)
    fps = output_cfg.get("fps", 30)
    crf = output_cfg.get("crf", 20)
    scene_padding = assets_cfg.get("scene_padding", 0.3)

    project_dir = Path(__file__).parent.resolve()
    # Use per-video tmp directory to avoid cross-contamination
    script_name = Path(args.script).stem
    tmp_dir = str(project_dir / "tmp" / script_name)
    remotion_dir = str(project_dir / "remotion")
    output_dir = str(project_dir / "output")

    Path(tmp_dir).mkdir(parents=True, exist_ok=True)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # --- Stage 1: Parse script ---
    print("=" * 50)
    print("STAGE 1: Parsing script...")
    script = parse_script(args.script)
    print(f"  Title: {script.title}")
    print(f"  Scenes: {len(script.scenes)}")
    print(f"  Voice: {script.voice}")
    if script.hook:
        print(f"  Hook: \"{script.hook.text}\" ({script.hook.duration}s, {script.hook.style})")

    # --- Stage 2: Fetch assets ---
    print("=" * 50)
    print("STAGE 2: Fetching assets...")
    if args.skip_assets:
        print("  Skipped (--skip-assets)")
        # Try to load cached asset paths
        for scene in script.scenes:
            for ext in ["mp4", "jpg"]:
                cached = str(Path(tmp_dir) / "assets" / f"scene_{scene.index:03d}.{ext}")
                if os.path.exists(cached):
                    scene.asset_path = cached
                    break
    else:
        pexels_key = api_keys.get("pexels", "")
        pixabay_key = api_keys.get("pixabay")
        google_api_key = api_keys.get("google_api_key", "")
        google_cx = api_keys.get("google_cx", "")
        serpapi_key = api_keys.get("serpapi_key", "")
        for scene in script.scenes:
            if scene.visuals.type in ("stock_video", "stock_image", "news_image") and scene.visuals.query:
                print(f"  Scene {scene.index}: fetching {scene.visuals.type} for '{scene.visuals.query}'...")
                asset_path = fetch_asset(
                    scene.index,
                    scene.visuals.type,
                    scene.visuals.query,
                    pexels_key,
                    pixabay_key,
                    tmp_dir,
                    max_video_length=assets_cfg.get("max_video_length", 15),
                    google_api_key=google_api_key,
                    google_cx=google_cx,
                    serpapi_key=serpapi_key,
                )
                scene.asset_path = asset_path
                if asset_path:
                    print(f"    → {asset_path}")
                else:
                    print(f"    → No asset found, will use fallback color")
                time.sleep(0.5)  # Rate limiting

    # --- Stage 3: Generate TTS ---
    print("=" * 50)
    print("STAGE 3: Generating TTS narration...")
    voice_cache = {}
    if args.skip_tts:
        print("  Skipped (--skip-tts)")
        # Load cached audio and probe durations
        from pipeline.tts import get_audio_duration
        for scene in script.scenes:
            cached = str(Path(tmp_dir) / "audio" / f"scene_{scene.index:03d}.mp3")
            if os.path.exists(cached):
                scene.audio_path = cached
                scene.audio_duration = get_audio_duration(cached)
    else:
        elevenlabs_key = api_keys.get("elevenlabs", "")
        fish_audio_key = api_keys.get("fish_audio", "")
        fish_audio_ref = tts_cfg.get("fish_audio_reference_id")
        if not elevenlabs_key and not fish_audio_key:
            print("  Warning: No ElevenLabs or Fish.audio API key. Skipping TTS.")
        else:
            for scene in script.scenes:
                if not scene.narration:
                    continue
                audio_path = str(Path(tmp_dir) / "audio" / f"scene_{scene.index:03d}.mp3")
                print(f"  Scene {scene.index}: generating audio...")
                duration = generate_tts(
                    api_key=elevenlabs_key,
                    text=scene.narration,
                    output_path=audio_path,
                    voice_name=script.voice or tts_cfg.get("default_voice", "adam"),
                    model=tts_cfg.get("model", "eleven_multilingual_v2"),
                    stability=tts_cfg.get("stability", 0.5),
                    similarity_boost=tts_cfg.get("similarity_boost", 0.75),
                    voice_id_cache=voice_cache,
                    fish_audio_api_key=fish_audio_key or None,
                    fish_audio_reference_id=fish_audio_ref,
                )
                scene.audio_path = audio_path
                scene.audio_duration = duration
                print(f"    → {duration:.2f}s")

    # --- Stage 4: Render Remotion overlays ---
    print("=" * 50)
    print("STAGE 4: Rendering text overlays...")
    overlay_path = str(Path(tmp_dir) / "overlays" / "overlay.mov")
    if args.skip_remotion:
        print("  Skipped (--skip-remotion)")
        if not os.path.exists(overlay_path):
            overlay_path = None
    else:
        try:
            overlay_path = render_overlays(
                scenes=script.scenes,
                remotion_dir=remotion_dir,
                tmp_dir=tmp_dir,
                fps=fps,
                timeout=remotion_cfg.get("timeout", 300),
                hook=script.hook,
                show_character=script.character,
            )
            print(f"  → {overlay_path}")
        except Exception as e:
            print(f"  Warning: Remotion render failed: {e}")
            print("  Continuing without overlays...")
            overlay_path = None

    # --- Stage 5: Final compositing ---
    print("=" * 50)
    print("STAGE 5: Compositing final video...")

    # Build background
    print("  Building background track...")
    hook_duration = script.hook.duration if script.hook else 0.0
    bg_path = build_background(
        script.scenes, tmp_dir, width, height, fps, scene_padding,
        hook_duration=hook_duration,
    )

    # Build audio track (add silence for hook duration at the start)
    print("  Building audio track...")
    audio_path = build_audio(script.scenes, tmp_dir, scene_padding,
                             hook_duration=hook_duration)

    # Determine output path
    if args.output:
        final_output = str(Path(output_dir) / args.output)
    else:
        final_output = str(Path(output_dir) / f"{slugify(script.title)}.mp4")

    # Compose
    print("  Composing final video...")
    compose_final(
        background_path=bg_path,
        overlay_path=overlay_path,
        audio_path=audio_path,
        music_path=script.music,
        output_path=final_output,
        width=width,
        height=height,
        fps=fps,
        crf=crf,
    )

    print("=" * 50)
    print(f"Done! Output: {final_output}")
    file_size = os.path.getsize(final_output) / (1024 * 1024)
    print(f"File size: {file_size:.1f} MB")


if __name__ == "__main__":
    main()
