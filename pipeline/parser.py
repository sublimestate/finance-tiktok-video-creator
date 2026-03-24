"""Parse YAML video scripts into Scene dataclasses."""

import yaml
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path


@dataclass
class TextOverlay:
    content: str = ""
    style: str = "title"  # title | subtitle | lower_third | typewriter
    position: str = "center"  # center | top | bottom


@dataclass
class Visuals:
    type: str = "solid_color"  # stock_video | stock_image | solid_color
    query: str = ""
    fallback_color: str = "#1a1a2e"


@dataclass
class WordTiming:
    word: str = ""
    start: float = 0.0  # seconds
    end: float = 0.0  # seconds


@dataclass
class Scene:
    index: int = 0
    narration: str = ""
    duration: Optional[float] = None  # None means auto (derived from TTS)
    visuals: Visuals = field(default_factory=Visuals)
    text_overlay: Optional[TextOverlay] = None
    icon: Optional[str] = None
    # Populated by later pipeline stages
    audio_path: Optional[str] = None
    audio_duration: Optional[float] = None
    asset_path: Optional[str] = None
    overlay_path: Optional[str] = None
    word_timings: List[WordTiming] = field(default_factory=list)


@dataclass
class Hook:
    text: str = ""
    duration: float = 1.5  # seconds the hook displays before narration starts
    style: str = "bold"  # bold | glitch | zoom


@dataclass
class Script:
    title: str = "Untitled"
    voice: str = "adam"
    music: Optional[str] = None
    hook: Optional[Hook] = None
    character: bool = False  # Show animated avatar character
    scenes: List[Scene] = field(default_factory=list)


def parse_script(path: str) -> Script:
    """Parse a YAML script file into a Script object."""
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    hook = None
    hook_data = data.get("hook")
    if hook_data:
        if isinstance(hook_data, str):
            hook = Hook(text=hook_data)
        else:
            hook = Hook(
                text=hook_data.get("text", ""),
                duration=float(hook_data.get("duration", 1.5)),
                style=hook_data.get("style", "bold"),
            )

    script = Script(
        title=data.get("title", "Untitled"),
        voice=data.get("voice", "adam"),
        music=data.get("music"),
        hook=hook,
        character=data.get("character", False),
    )

    for i, scene_data in enumerate(data.get("scenes", [])):
        visuals_data = scene_data.get("visuals", {})
        visuals = Visuals(
            type=visuals_data.get("type", "solid_color"),
            query=visuals_data.get("query", ""),
            fallback_color=visuals_data.get("fallback_color", "#1a1a2e"),
        )

        text_data = scene_data.get("text_overlay")
        text_overlay = None
        if text_data:
            text_overlay = TextOverlay(
                content=text_data.get("content", ""),
                style=text_data.get("style", "title"),
                position=text_data.get("position", "center"),
            )

        duration_raw = scene_data.get("duration", "auto")
        duration = None if duration_raw == "auto" else float(duration_raw)

        scene = Scene(
            index=i,
            narration=scene_data.get("narration", ""),
            duration=duration,
            visuals=visuals,
            text_overlay=text_overlay,
            icon=scene_data.get("icon"),
        )
        script.scenes.append(scene)

    return script
