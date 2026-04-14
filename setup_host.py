#!/usr/bin/env python3
"""One-shot: generate the recurring AI host portrait via Replicate Flux.

Run once (or with --regenerate) before using host_video.py.
"""
import argparse
import os
import sys
import time
from pathlib import Path
from typing import List

from PIL import Image

from avatar.character import save_character

DEFAULT_VOICE = "en-GB-RyanNeural"
DEFAULT_NAME = "Ryan"
NUM_CANDIDATES = 4
AVATAR_DIR = Path(__file__).parent / "data" / "avatar"


def build_flux_prompt(name: str = DEFAULT_NAME) -> str:
    """The constraint set baked into the spec.

    Keep this deterministic and self-contained so tests can assert on it
    without hitting the Replicate API.
    """
    return (
        f"Photorealistic portrait of {name}, a 32-year-old British man, "
        "head and shoulders framing, looking slightly off-center toward the camera, "
        "neutral expression, neutral background, "
        "lighting from the front-left, soft studio light, "
        "high detail, sharp focus, professional headshot, no glasses, no logos"
    )


def tile_candidates_2x2(candidate_paths: List[Path], output_path: Path) -> Path:
    """Tile 4 square portraits into a 2x2 preview image at full resolution.

    Output dimensions are (2*side, 2*side) where side is the input image side length.
    """
    if len(candidate_paths) != 4:
        raise ValueError(f"expected 4 candidates, got {len(candidate_paths)}")
    images = [Image.open(p).convert("RGB") for p in candidate_paths]
    side = images[0].size[0]
    canvas = Image.new("RGB", (side * 2, side * 2))
    for idx, img in enumerate(images):
        x = (idx % 2) * side
        y = (idx // 2) * side
        canvas.paste(img, (x, y))
    canvas.save(output_path)
    return output_path


def generate_candidates(prompt: str, out_dir: Path) -> List[Path]:
    """Call Replicate Flux to generate NUM_CANDIDATES portrait variants.

    Each call produces one image. The Flux model returns image URLs we
    download into out_dir.
    """
    import replicate
    import requests

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for i in range(NUM_CANDIDATES):
        last_exc = None
        for attempt, delay in enumerate([0, 5, 10]):
            if delay:
                print(f"  retrying candidate {i+1} after {delay}s (attempt {attempt+1})...")
                time.sleep(delay)
            try:
                output = replicate.run(
                    "black-forest-labs/flux-schnell",
                    input={
                        "prompt": prompt,
                        "aspect_ratio": "1:1",
                        "num_outputs": 1,
                        "output_format": "png",
                        "output_quality": 95,
                    },
                )
                break
            except Exception as exc:
                last_exc = exc
        else:
            raise RuntimeError(f"replicate failed after 3 attempts for candidate {i+1}: {last_exc}")
        # Replicate returns a list of FileOutput objects (or URL strings for older models)
        url = output[0] if isinstance(output, list) else output
        url_str = str(url)
        resp = requests.get(url_str, timeout=60)
        resp.raise_for_status()
        path = out_dir / f"candidate_{i+1}.png"
        path.write_bytes(resp.content)
        paths.append(path)
        print(f"  generated candidate {i+1}/{NUM_CANDIDATES}")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the recurring AI host portrait")
    parser.add_argument("--regenerate", action="store_true",
                        help="Re-run candidate generation even if a portrait exists")
    parser.add_argument("--prompt", default=None,
                        help="Override the default Flux prompt")
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    args = parser.parse_args()

    if (AVATAR_DIR / "portrait.png").exists() and not args.regenerate:
        print(f"Portrait already exists at {AVATAR_DIR / 'portrait.png'}")
        print("Pass --regenerate to overwrite (the previous portrait is backed up to portrait.png.bak)")
        return 0

    # Token check — only runs when we actually need to call Replicate
    if not os.environ.get("REPLICATE_API_TOKEN"):
        print("Error: REPLICATE_API_TOKEN environment variable not set.")
        print("Get a token from https://replicate.com/account/api-tokens")
        print("Then run: export REPLICATE_API_TOKEN=<your-token>")
        return 1

    prompt = args.prompt or build_flux_prompt(args.name)
    print(f"Prompt: {prompt}\n")

    candidates_dir = AVATAR_DIR / "candidates"
    candidate_paths = generate_candidates(prompt, candidates_dir)

    preview_path = candidates_dir / "preview.png"
    tile_candidates_2x2(candidate_paths, preview_path)
    print(f"\nPreview image: {preview_path}")
    print("Open it in any image viewer to inspect the 4 candidates.\n")

    while True:
        choice = input("Pick a candidate (1-4) or 'q' to abort: ").strip()
        if choice == "q":
            return 1
        if choice in ("1", "2", "3", "4"):
            chosen_path = candidate_paths[int(choice) - 1]
            break
        print("Please enter 1, 2, 3, 4, or q.")

    portrait_bytes = chosen_path.read_bytes()
    char = save_character(
        portrait_bytes=portrait_bytes,
        prompt=prompt,
        voice=args.voice,
        name=args.name,
        avatar_dir=AVATAR_DIR,
    )
    print(f"\nSaved portrait → {char.portrait_path}")
    print(f"Saved character config → {AVATAR_DIR / 'character.yaml'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
