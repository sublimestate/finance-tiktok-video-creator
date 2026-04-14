"""FFmpeg final compositing: background + overlay + audio → output MP4."""

import subprocess
import os
from pathlib import Path
from typing import Dict, List, Optional

from pipeline.parser import Scene
from platform_utils import get_video_encode_args, get_video_encode_args_simple


def _create_color_clip(color: str, duration: float, output_path: str,
                       width: int = 1080, height: int = 1920, fps: int = 30) -> None:
    """Create a solid color video clip."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"color=c={color}:s={width}x{height}:d={duration}:r={fps}",
         *get_video_encode_args_simple(), output_path],
        capture_output=True,
    )


def _create_ken_burns(image_path: str, duration: float, output_path: str,
                      width: int = 1080, height: int = 1920, fps: int = 30) -> None:
    """Create a clip from a still image with blurred background + slow zoom on the foreground."""
    frames = int(duration * fps)
    # Two-pass: first resize image to manageable size, then compose
    # Step 1: Pre-resize the image to limit processing
    tmp_resized = output_path + "_resized.jpg"
    subprocess.run(
        ["ffmpeg", "-y", "-i", image_path,
         "-vf", f"scale=1080:-1",
         "-q:v", "2", tmp_resized],
        capture_output=True, timeout=15,
    )
    src = tmp_resized if os.path.exists(tmp_resized) and os.path.getsize(tmp_resized) > 0 else image_path

    # Step 2: Create blurred bg + foreground with slow zoom
    result = subprocess.run(
        ["ffmpeg", "-y", "-loop", "1", "-i", src,
         "-filter_complex", (
             # Blurred background layer
             f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
             f"crop={width}:{height},boxblur=20:5[bg];"
             # Foreground with slow zoom (1.0 -> 1.08)
             f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
             f"zoompan=z='1+0.08*on/{frames}':"
             f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
             f"d={frames}:s={width}x{height}:fps={fps}[fg];"
             # Overlay fg on bg
             f"[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1[out]"
         ),
         "-map", "[out]",
         "-t", str(duration),
         "-r", str(fps),
         *get_video_encode_args_simple(), output_path],
        capture_output=True,
        timeout=180,
    )

    # Clean up temp file
    if os.path.exists(tmp_resized):
        os.unlink(tmp_resized)

    # If zoompan failed (timeout), fall back to static
    if result.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", image_path,
             "-filter_complex", (
                 f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                 f"crop={width}:{height},boxblur=20:5[bg];"
                 f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
                 f"[bg][fg]overlay=(W-w)/2:(H-h)/2[out]"
             ),
             "-map", "[out]",
             "-t", str(duration),
             "-r", str(fps),
             *get_video_encode_args_simple(), output_path],
            capture_output=True,
            timeout=120,
        )


def build_background(scenes: List[Scene], tmp_dir: str,
                     width: int = 1080, height: int = 1920,
                     fps: int = 30, scene_padding: float = 0.3,
                     hook_duration: float = 0.0,
                     cutaway_overrides: Optional[Dict[int, str]] = None) -> str:
    """Build the concatenated background video from scene assets.

    Args:
        scenes: List of Scene objects with asset_path pre-fetched.
        tmp_dir: Temporary directory for intermediate files.
        width: Output video width in pixels (default 1080).
        height: Output video height in pixels (default 1920).
        fps: Output frame rate (default 30).
        scene_padding: Seconds of extra duration added to each scene (default 0.3).
        hook_duration: Duration of the hook lead-in segment in seconds (default 0.0).
        cutaway_overrides: Optional mapping of scene.index → pre-rendered mp4 path.
            When a scene's index is present in this dict, the provided mp4 is used
            as the source for that scene's segment instead of the normal stock-asset
            path (scale/crop for videos, ken-burns for images, solid color fallback).
    """
    bg_dir = Path(tmp_dir) / "background"
    bg_dir.mkdir(parents=True, exist_ok=True)

    segment_paths = []

    # If there's a hook, extend the first scene's background or create a lead-in
    # from the first scene's asset to cover the hook duration
    if hook_duration > 0 and scenes:
        first_scene = scenes[0]
        hook_seg = str(bg_dir / "hook.mp4")
        if first_scene.visuals.type in ("stock_video", "news_video") and first_scene.asset_path:
            subprocess.run(
                ["ffmpeg", "-y", "-i", first_scene.asset_path,
                 "-vf", (
                     f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                     f"crop={width}:{height},setsar=1"
                 ),
                 "-t", str(hook_duration),
                 *get_video_encode_args_simple(),
                 "-r", str(fps), "-an", hook_seg],
                capture_output=True,
            )
        elif first_scene.visuals.type in ("stock_image", "news_image") and first_scene.asset_path:
            _create_ken_burns(first_scene.asset_path, hook_duration, hook_seg, width, height, fps)
        else:
            _create_color_clip(
                first_scene.visuals.fallback_color, hook_duration, hook_seg, width, height, fps
            )
        segment_paths.append(hook_seg)

    for scene in scenes:
        duration = (scene.audio_duration or scene.duration or 3.0) + scene_padding
        seg_path = str(bg_dir / f"scene_{scene.index:03d}.mp4")

        cutaway = (cutaway_overrides or {}).get(scene.index)
        if cutaway:
            # Cutaway override: use the provided pre-rendered mp4 as the
            # source for this scene. Re-encode through the same scale/crop
            # path as stock videos so it integrates with the concat.
            subprocess.run(
                ["ffmpeg", "-y", "-i", cutaway,
                 "-vf", (
                     f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                     f"crop={width}:{height},setsar=1"
                 ),
                 "-t", str(duration),
                 *get_video_encode_args_simple(),
                 "-r", str(fps), "-an", seg_path],
                capture_output=True,
            )
            segment_paths.append(seg_path)
            continue

        if scene.visuals.type in ("stock_video", "news_video") and scene.asset_path:
            # Scale and pad stock video to exact dimensions and duration
            subprocess.run(
                ["ffmpeg", "-y", "-i", scene.asset_path,
                 "-vf", (
                     f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                     f"crop={width}:{height},setsar=1"
                 ),
                 "-t", str(duration),
                 *get_video_encode_args_simple(),
                 "-r", str(fps), "-an", seg_path],
                capture_output=True,
            )
        elif scene.visuals.type in ("stock_image", "news_image") and scene.asset_path:
            _create_ken_burns(scene.asset_path, duration, seg_path, width, height, fps)
        else:
            _create_color_clip(
                scene.visuals.fallback_color, duration, seg_path, width, height, fps
            )

        segment_paths.append(seg_path)

    # Write concat list
    concat_list_path = str(bg_dir / "concat.txt")
    with open(concat_list_path, "w") as f:
        for p in segment_paths:
            f.write(f"file '{p}'\n")

    output_path = str(Path(tmp_dir) / "background_concat.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", concat_list_path, "-c", "copy", output_path],
        capture_output=True,
    )
    return output_path


def build_audio(scenes: List[Scene], tmp_dir: str,
                scene_padding: float = 0.3,
                hook_duration: float = 0.0) -> str:
    """Concatenate scene audio clips with padding silence."""
    audio_dir = Path(tmp_dir) / "audio_build"
    audio_dir.mkdir(parents=True, exist_ok=True)

    segment_paths = []

    # Prepend silence for hook duration
    if hook_duration > 0:
        hook_silence = str(audio_dir / "hook_silence.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"anullsrc=r=44100:cl=stereo",
             "-t", str(hook_duration),
             "-c:a", "libmp3lame", hook_silence],
            capture_output=True,
        )
        segment_paths.append(hook_silence)

    for scene in scenes:
        if not scene.audio_path:
            continue

        # Add silence padding after each clip
        padded_path = str(audio_dir / f"scene_{scene.index:03d}_padded.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-i", scene.audio_path,
             "-af", f"apad=pad_dur={scene_padding}",
             "-c:a", "libmp3lame", padded_path],
            capture_output=True,
        )
        segment_paths.append(padded_path)

    if not segment_paths:
        # Generate silence
        silence_path = str(Path(tmp_dir) / "audio_concat.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-t", "1", "-c:a", "libmp3lame", silence_path],
            capture_output=True,
        )
        return silence_path

    concat_list_path = str(audio_dir / "concat.txt")
    with open(concat_list_path, "w") as f:
        for p in segment_paths:
            f.write(f"file '{p}'\n")

    output_path = str(Path(tmp_dir) / "audio_concat.mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", concat_list_path, "-c", "copy", output_path],
        capture_output=True,
    )
    return output_path


def compose_final(
    background_path: str,
    overlay_path: Optional[str],
    audio_path: str,
    music_path: Optional[str],
    output_path: str,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    crf: int = 20,
) -> str:
    """Compose final video: background + overlay + audio (+ optional music)."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    inputs = ["-i", background_path]
    filter_parts = []
    has_overlay = overlay_path and os.path.exists(overlay_path)
    map_video = "0:v"

    # Add overlay if it exists
    if has_overlay:
        inputs += ["-i", overlay_path]
        filter_parts.append("[0:v][1:v]overlay=0:0[vout]")
        map_video = "[vout]"

    # Add narration audio
    inputs += ["-i", audio_path]
    audio_input_idx = 2 if has_overlay else 1

    if music_path and os.path.exists(music_path):
        inputs += ["-i", music_path]
        music_idx = audio_input_idx + 1
        # Mix narration at full volume, music at 15%
        filter_parts.append(
            f"[{music_idx}:a]volume=0.15[bgm];"
            f"[{audio_input_idx}:a][bgm]amix=inputs=2:duration=first[aout]"
        )
        audio_map = "[aout]"
    else:
        audio_map = f"{audio_input_idx}:a"

    filter_complex = ";".join(filter_parts) if filter_parts else None

    cmd = ["ffmpeg", "-y"] + inputs

    if filter_complex:
        cmd += ["-filter_complex", filter_complex]

    cmd += [
        "-map", map_video,
        "-map", audio_map,
    ] + get_video_encode_args(crf=crf, preset="medium") + [
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(fps),
        "-s", f"{width}x{height}",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg compose failed:\n{result.stderr}")

    return output_path
