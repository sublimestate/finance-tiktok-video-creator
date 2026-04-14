"""Recurring AI host character config — load and save.

The character is generated once by setup_host.py and reused forever.
This module owns the on-disk format under data/avatar/.
"""
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml


@dataclass
class Character:
    name: str
    voice: str
    prompt_used: str
    created: str
    portrait_path: Path


def _config_path(avatar_dir: Path) -> Path:
    return avatar_dir / "character.yaml"


def _portrait_path(avatar_dir: Path) -> Path:
    return avatar_dir / "portrait.png"


def _backup_path(avatar_dir: Path) -> Path:
    return avatar_dir / "portrait.png.bak"


def load_character(avatar_dir: Path) -> Character:
    config = _config_path(avatar_dir)
    portrait = _portrait_path(avatar_dir)
    if not config.exists() or not portrait.exists():
        raise FileNotFoundError(
            f"No host character found in {avatar_dir}. "
            "Run `python3 setup_host.py` first to generate one."
        )
    data = yaml.safe_load(config.read_text())
    return Character(
        name=data["name"],
        voice=data["voice"],
        prompt_used=data["prompt_used"],
        created=str(data["created"]),
        portrait_path=portrait,
    )


def save_character(
    portrait_bytes: bytes,
    prompt: str,
    voice: str,
    name: str,
    avatar_dir: Path,
) -> Character:
    avatar_dir.mkdir(parents=True, exist_ok=True)
    portrait = _portrait_path(avatar_dir)
    if portrait.exists():
        # Preserve previous portrait so a regenerate is reversible
        _backup_path(avatar_dir).write_bytes(portrait.read_bytes())
    portrait.write_bytes(portrait_bytes)

    today = date.today().isoformat()
    _config_path(avatar_dir).write_text(
        yaml.safe_dump(
            {"name": name, "voice": voice, "prompt_used": prompt, "created": today},
            sort_keys=False,
        )
    )
    return Character(
        name=name,
        voice=voice,
        prompt_used=prompt,
        created=today,
        portrait_path=portrait,
    )
