"""Tests for avatar/character.py — loading and saving the recurring host config."""
from pathlib import Path

import pytest

from avatar.character import Character, load_character, save_character


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    portrait_bytes = b"\x89PNG\r\n\x1a\nfake-png-content"
    save_character(
        portrait_bytes=portrait_bytes,
        prompt="head and shoulders portrait",
        voice="en-GB-RyanNeural",
        name="Ryan",
        avatar_dir=tmp_path,
    )

    assert (tmp_path / "portrait.png").read_bytes() == portrait_bytes

    char = load_character(avatar_dir=tmp_path)
    assert char.name == "Ryan"
    assert char.voice == "en-GB-RyanNeural"
    assert char.prompt_used == "head and shoulders portrait"
    assert char.portrait_path == tmp_path / "portrait.png"


def test_save_creates_backup_of_existing_portrait(tmp_path: Path) -> None:
    save_character(
        portrait_bytes=b"old-portrait",
        prompt="old",
        voice="en-GB-RyanNeural",
        name="Old",
        avatar_dir=tmp_path,
    )
    save_character(
        portrait_bytes=b"new-portrait",
        prompt="new",
        voice="en-GB-RyanNeural",
        name="New",
        avatar_dir=tmp_path,
    )

    assert (tmp_path / "portrait.png").read_bytes() == b"new-portrait"
    assert (tmp_path / "portrait.png.bak").read_bytes() == b"old-portrait"


def test_load_missing_character_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="setup_host.py"):
        load_character(avatar_dir=tmp_path)
