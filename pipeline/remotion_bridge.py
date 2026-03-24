"""Bridge between Python pipeline and Remotion CLI for rendering overlays."""

import json
import subprocess
from pathlib import Path
from typing import List

from pipeline.parser import Scene, Hook
from typing import Optional


def build_remotion_props(scenes: List[Scene], fps: int = 30, hook: Optional[Hook] = None, show_character: bool = False) -> dict:
    """Convert scene list to Remotion-compatible props JSON."""
    remotion_scenes = []

    # Hook takes up time at the start
    hook_data = None
    hook_frames = 0
    if hook and hook.text:
        hook_frames = int(hook.duration * fps)
        hook_data = {
            "text": hook.text,
            "durationInFrames": hook_frames,
            "style": hook.style,
        }

    total_frames = hook_frames

    for scene in scenes:
        duration = scene.audio_duration or scene.duration or 3.0
        frame_count = int(duration * fps)

        remotion_scene = {
            "index": scene.index,
            "durationInFrames": frame_count,
            "startFrame": total_frames,
            "narration": scene.narration,
            "textOverlay": None,
            "icon": scene.icon,
        }

        if scene.text_overlay:
            remotion_scene["textOverlay"] = {
                "content": scene.text_overlay.content,
                "style": scene.text_overlay.style,
                "position": scene.text_overlay.position,
            }

        remotion_scenes.append(remotion_scene)
        total_frames += frame_count

    return {
        "hook": hook_data,
        "scenes": remotion_scenes,
        "totalDurationInFrames": total_frames,
        "fps": fps,
        "width": 1080,
        "height": 1920,
        "showCharacter": show_character,
    }


def render_overlays(
    scenes: List[Scene],
    remotion_dir: str,
    tmp_dir: str,
    fps: int = 30,
    timeout: int = 300,
    hook: Optional[Hook] = None,
    show_character: bool = False,
) -> str:
    """Render the overlay video using Remotion CLI.

    Returns path to the rendered overlay video (MOV with alpha).
    """
    props = build_remotion_props(scenes, fps, hook=hook, show_character=show_character)
    props_path = str(Path(tmp_dir) / "remotion_input.json")
    png_dir = str(Path(tmp_dir) / "overlays" / "frames")
    output_path = str(Path(tmp_dir) / "overlays" / "overlay.mov")

    Path(props_path).parent.mkdir(parents=True, exist_ok=True)
    Path(png_dir).mkdir(parents=True, exist_ok=True)

    with open(props_path, "w") as f:
        json.dump(props, f, indent=2)

    # Render as PNG sequence (preserves alpha)
    cmd = [
        "npx", "remotion", "render",
        "src/index.tsx",
        "FinanceOverlay",
        "--props", props_path,
        "--image-format", "png",
        "--sequence",
        "--output", png_dir,
        "--height", "1920",
        "--width", "1080",
    ]

    result = subprocess.run(
        cmd,
        cwd=remotion_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Remotion render failed:\n{result.stderr}\n{result.stdout}"
        )

    # Rename frames to zero-padded format for FFmpeg
    import glob
    import re
    frames = glob.glob(str(Path(png_dir) / "element-*.png"))
    for frame_path in frames:
        basename = Path(frame_path).name
        match = re.match(r"element-(\d+)\.png", basename)
        if match:
            num = int(match.group(1))
            new_name = Path(frame_path).parent / f"frame-{num:06d}.png"
            Path(frame_path).rename(new_name)

    # Convert PNG sequence to MOV with alpha
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(Path(png_dir) / "frame-%06d.png"),
        "-c:v", "png",
        "-pix_fmt", "rgba",
        output_path,
    ]

    result = subprocess.run(
        ffmpeg_cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg PNG→MOV conversion failed:\n{result.stderr}"
        )

    return output_path
