#!/usr/bin/env python3
"""host_video.py — headline → AI-host-cutaway TikTok video.

End-to-end:
  1. Research topic (reuse quick_video.research_topic)
  2. AI script generation (pipeline.host_script.generate_host_script)
  3. Save script YAML, parse via pipeline.parser
  4. Per-scene asset fetch (existing pipeline.assets.fetch_asset)
  5. Per-scene TTS (existing pipeline.tts.generate_tts)
  6. Render avatar cutaways for host beats via avatar.render.render_cutaways_batch
  7. build_background(scene, ..., cutaway_overrides=...)
  8. build_audio + compose_final → final mp4

Output: output/host/<slug>.mp4

For v1, TTS and pod boot run sequentially. The "parallel pod boot during
TTS" optimization from the spec is deferred — single-pod batching
still gives most of the cost benefit.
"""
import argparse
import os
import sys
import time
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from slugify import slugify

# Existing pipeline
from quick_video import research_topic
from pipeline.host_script import generate_host_script, host_beat_indices
from pipeline.parser import parse_script, WordTiming
from pipeline.tts import generate_tts
from pipeline.assets import fetch_asset
from pipeline.composer import build_background, build_audio, compose_final
from pipeline.remotion_bridge import render_overlays

# New avatar module
from avatar.character import load_character
from avatar.render import render_cutaways_batch, render_still_portrait_fallback

PROJECT_DIR = Path(__file__).parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
AVATAR_DIR = DATA_DIR / "avatar"
OUTPUT_DIR = PROJECT_DIR / "output" / "host"
DEFAULT_IMAGE = os.environ.get(
    "RUNPOD_IMAGE", "<dockerhub-user>/musetalk-runpod:0.1.0"
)


def load_config(config_path: str = "config.yaml") -> dict:
    if not os.path.exists(config_path):
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


def pair_host_beats_with_audio(scenes, host_indices: List[int]) -> List[Tuple[int, Path]]:
    """Return [(scene_index, audio_path), ...] for host beat scenes that have audio.

    Scenes whose TTS failed (audio_path is None) are skipped so they fall
    through to the composer's normal collage rendering path.
    """
    pairs: List[Tuple[int, Path]] = []
    for scene in scenes:
        if scene.index in host_indices and scene.audio_path:
            pairs.append((scene.index, Path(scene.audio_path)))
    return pairs


def build_cutaway_override_map(
    host_indices: List[int], cutaway_paths: List[Path]
) -> Dict[int, str]:
    """Convert two parallel lists into the dict shape build_background expects.

    host_indices and cutaway_paths must be the same length and ordered
    correspondingly (i.e., cutaway_paths[i] is the rendered cutaway for
    scene index host_indices[i]).
    """
    if len(host_indices) != len(cutaway_paths):
        raise ValueError(
            f"length mismatch: {len(host_indices)} host indices vs "
            f"{len(cutaway_paths)} cutaway paths"
        )
    return {idx: str(path) for idx, path in zip(host_indices, cutaway_paths)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a TikTok video with an AI host as cutaways"
    )
    parser.add_argument("headline", nargs="+", help="One-line news headline")
    parser.add_argument("--config", "-c", default="config.yaml")
    parser.add_argument("--image", default=DEFAULT_IMAGE,
                        help="MuseTalk worker image to use on RunPod")
    parser.add_argument("--no-runpod", action="store_true",
                        help="Skip RunPod entirely; all host beats use still-portrait fallback")
    args = parser.parse_args()

    headline = " ".join(args.headline)
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

    # 1. Load character — fails fast if setup_host hasn't run
    character = load_character(AVATAR_DIR)
    print(f"Host: {character.name} ({character.voice})")
    print(f"Headline: {headline}")
    print("=" * 50)

    # 2. Research topic
    print("STAGE 1: Researching topic...")
    research = research_topic(headline)
    print(f"  Found {len(research)} chars of research" if research else "  (no extra context)")

    # 3. Generate script with host beats
    print("=" * 50)
    print("STAGE 2: Generating script with OCI Gemini...")
    script_data = generate_host_script(headline, research)
    script_data["voice"] = character.voice
    indices = host_beat_indices(script_data)
    print(f"  Title: {script_data.get('title', '?')}")
    print(f"  Scenes: {len(script_data.get('scenes', []))}, host beats: {indices}")

    # Compute slug once for both fallback and main paths
    slug = slugify(script_data.get("title", headline))[:40]

    # No-host-beats fallback: shell out to quick_video for a normal collage video
    if not indices:
        print("  AI returned 0 host beats — falling back to standard collage video.")
        script_path = PROJECT_DIR / "scripts" / f"{slug}.yaml"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        with open(script_path, "w") as f:
            yaml.dump(script_data, f, default_flow_style=False, allow_unicode=True)
        rc = os.system(f"cd {PROJECT_DIR} && python3 create_video.py {script_path}")
        return rc >> 8

    # 4. Save script YAML so the existing parser can load it
    script_path = PROJECT_DIR / "scripts" / f"{slug}.yaml"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    with open(script_path, "w") as f:
        yaml.dump(script_data, f, default_flow_style=False, allow_unicode=True)
    print(f"  Saved script: {script_path}")

    script = parse_script(str(script_path))
    tmp_dir = str(PROJECT_DIR / "tmp" / slug)
    Path(tmp_dir).mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 5. Fetch assets for non-host scenes (host scenes don't need stock visuals)
    print("=" * 50)
    print("STAGE 3: Fetching assets...")
    pexels_key = api_keys.get("pexels", "")
    pixabay_key = api_keys.get("pixabay")
    google_api_key = api_keys.get("google_api_key", "")
    google_cx = api_keys.get("google_cx", "")
    serpapi_key = api_keys.get("serpapi_key", "")
    for scene in script.scenes:
        if scene.index in indices:
            continue  # Host beat — composer will use cutaway override
        if scene.visuals.type in ("stock_video", "stock_image", "news_image", "news_video") and scene.visuals.query:
            print(f"  Scene {scene.index}: fetching {scene.visuals.type} for '{scene.visuals.query}'...")
            asset_path = fetch_asset(
                scene.index, scene.visuals.type, scene.visuals.query,
                pexels_key, pixabay_key, tmp_dir,
                max_video_length=assets_cfg.get("max_video_length", 15),
                google_api_key=google_api_key,
                google_cx=google_cx,
                serpapi_key=serpapi_key,
            )
            scene.asset_path = asset_path
            time.sleep(0.5)

    # 6. TTS for ALL scenes (host beats need audio for the avatar; collage scenes for narration)
    print("=" * 50)
    print("STAGE 4: Generating TTS...")
    elevenlabs_key = api_keys.get("elevenlabs", "")
    fish_audio_key = api_keys.get("fish_audio", "")
    fish_audio_ref = tts_cfg.get("fish_audio_reference_id")
    voice_cache: Dict = {}
    for scene in script.scenes:
        if not scene.narration:
            continue
        audio_path = str(Path(tmp_dir) / "audio" / f"scene_{scene.index:03d}.mp3")
        Path(audio_path).parent.mkdir(parents=True, exist_ok=True)
        print(f"  Scene {scene.index}: generating audio...")
        try:
            duration, word_timings = generate_tts(
                api_key=elevenlabs_key,
                text=scene.narration,
                output_path=audio_path,
                voice_name=script.voice or character.voice,
                model=tts_cfg.get("model", "eleven_multilingual_v2"),
                stability=tts_cfg.get("stability", 0.5),
                similarity_boost=tts_cfg.get("similarity_boost", 0.75),
                voice_id_cache=voice_cache,
                fish_audio_api_key=fish_audio_key or None,
                fish_audio_reference_id=fish_audio_ref,
            )
        except Exception as tts_err:
            print(f"  Warning: TTS failed for scene {scene.index}: {tts_err}; scene will use collage fallback")
            scene.audio_path = None
            continue
        scene.audio_path = audio_path
        scene.audio_duration = duration
        scene.word_timings = [
            WordTiming(word=w["word"], start=w["start"], end=w["end"])
            for w in word_timings
        ]

    # 7. Render avatar cutaways
    print("=" * 50)
    print(f"STAGE 5: Rendering {len(indices)} avatar cutaways...")
    cutaway_dir = Path(tmp_dir) / "cutaways"
    cutaway_dir.mkdir(parents=True, exist_ok=True)
    host_pairs = pair_host_beats_with_audio(script.scenes, indices)
    cutaway_jobs = [
        (audio_path, cutaway_dir / f"cutaway_{idx}.mp4")
        for idx, audio_path in host_pairs
    ]
    if args.no_runpod:
        cutaway_paths: List[Path] = []
        for audio_path, output_path in cutaway_jobs:
            cutaway_paths.append(
                render_still_portrait_fallback(character.portrait_path, audio_path, output_path)
            )
    else:
        cutaway_paths = render_cutaways_batch(
            portrait_path=character.portrait_path,
            jobs=cutaway_jobs,
            image=args.image,
        )

    # 8. Render overlays via Remotion (existing pipeline)
    print("=" * 50)
    print("STAGE 6: Rendering text overlays...")
    overlay_path: Optional[str] = None
    try:
        overlay_path = render_overlays(
            scenes=script.scenes,
            remotion_dir=str(PROJECT_DIR / "remotion"),
            tmp_dir=tmp_dir,
            fps=fps,
            timeout=remotion_cfg.get("timeout", 300),
            hook=script.hook,
            show_character=script.character,
            scene_padding=scene_padding,
        )
    except Exception as e:
        print(f"  Warning: Remotion render failed: {e}; continuing without overlays")

    # 9. Build background with cutaway overrides
    print("=" * 50)
    print("STAGE 7: Compositing final video...")
    cutaway_overrides = build_cutaway_override_map([idx for (idx, _) in host_pairs], cutaway_paths)
    hook_duration = script.hook.duration if script.hook else 0.0
    bg_path = build_background(
        script.scenes, tmp_dir, width, height, fps, scene_padding,
        hook_duration=hook_duration,
        cutaway_overrides=cutaway_overrides,
    )
    audio_path = build_audio(script.scenes, tmp_dir, scene_padding,
                             hook_duration=hook_duration)

    final_output = str(OUTPUT_DIR / f"{slug}.mp4")
    compose_final(
        background_path=bg_path,
        overlay_path=overlay_path,
        audio_path=audio_path,
        music_path=script.music,
        output_path=final_output,
        width=width, height=height, fps=fps, crf=crf,
    )

    print("=" * 50)
    file_size = os.path.getsize(final_output) / (1024 * 1024)
    print(f"Done! {final_output} ({file_size:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
