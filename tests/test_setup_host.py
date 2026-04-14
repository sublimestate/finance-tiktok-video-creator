"""Tests for setup_host.py — the one-shot character portrait generator."""
from pathlib import Path

from PIL import Image

from setup_host import build_flux_prompt, tile_candidates_2x2


def test_build_flux_prompt_has_required_constraints() -> None:
    prompt = build_flux_prompt()
    # Each constraint from the spec must appear in the prompt
    for must_have in [
        "head and shoulders",
        "neutral background",
        "neutral expression",
        "front-left",
    ]:
        assert must_have in prompt, f"missing constraint: {must_have}"


def test_tile_candidates_2x2_produces_double_size_image(tmp_path: Path) -> None:
    candidates = []
    for i, color in enumerate(["red", "green", "blue", "yellow"]):
        img = Image.new("RGB", (256, 256), color=color)
        path = tmp_path / f"c{i}.png"
        img.save(path)
        candidates.append(path)

    tiled = tile_candidates_2x2(candidates, output_path=tmp_path / "preview.png")
    assert tiled.exists()
    with Image.open(tiled) as im:
        assert im.size == (512, 512)
