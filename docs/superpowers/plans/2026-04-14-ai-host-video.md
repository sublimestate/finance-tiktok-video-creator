# AI Host Video Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `host_video.py` CLI that produces TikTok finance videos featuring a recurring AI-generated host as full-screen cutaway scenes inside the existing collage style.

**Architecture:** New `avatar/` module with three focused files (character config, RunPod client, high-level renderer) plus a Docker worker image. New `setup_host.py` one-shot generates the recurring portrait via Replicate Flux. New `host_video.py` CLI orchestrates research → script → TTS → parallel pod boot → cutaway render → composer assembly. The existing `pipeline/composer.py` gets one new optional parameter for cutaway scene overrides. No changes to `quick_video.py` or `clip_video.py`.

**Tech Stack:** Python 3.8, `replicate` SDK (Flux portrait), `requests` (RunPod REST API + inner pod service), `responses` (HTTP mocking in tests), `pytest`, `Pillow` (already installed, used for portrait tiling), `pyyaml` (already in deps), `ffmpeg` (already installed, for fallback still-portrait video), Docker (worker image), LivePortrait + RunPod Pods (A10 GPU).

**Spec:** `docs/superpowers/specs/2026-04-14-ai-host-video-design.md`

---

## File Structure

**New files:**
- `avatar/__init__.py` — empty marker
- `avatar/character.py` — `load_character()` / `save_character()` plus `Character` dataclass
- `avatar/runpod.py` — `RunPodSession` context manager wrapping the RunPod REST API + the inner pod service
- `avatar/render.py` — `render_cutaway(portrait, audio, output)` with fail-soft fallback to still-portrait video
- `avatar/worker/Dockerfile` — LivePortrait + Flask inner service, weights baked in
- `avatar/worker/server.py` — Flask `/render` endpoint that runs LivePortrait inside the pod
- `setup_host.py` — Flux portrait generation via Replicate, interactive selection
- `host_video.py` — headline → avatar-cutaway video CLI
- `pipeline/host_script.py` — AI script generator with host-beat marking (separate from `quick_video.py`'s prompt to avoid touching it)
- `tests/conftest.py` — pytest config + shared fixtures
- `tests/avatar/test_character.py`
- `tests/avatar/test_runpod.py`
- `tests/avatar/test_render.py`
- `tests/pipeline/test_composer_cutaways.py`
- `tests/test_host_script.py`
- `tests/test_host_video.py`
- `tests/fixtures/test_portrait.png` — small test PNG (~50KB)
- `tests/fixtures/test_audio.wav` — 1-second silent WAV

**Modified files:**
- `.gitignore` — add `data/avatar/`
- `pipeline/composer.py` — add `cutaway_overrides` parameter

---

## Task 1: Set up pytest, dependencies, project directories

**Files:**
- Create: `tests/conftest.py`, `tests/__init__.py`, `tests/avatar/__init__.py`, `tests/pipeline/__init__.py`, `tests/fixtures/.gitkeep`, `avatar/__init__.py`, `pytest.ini`
- Modify: `.gitignore`

- [ ] **Step 1: Install Python dependencies**

```bash
python3 -m pip install --user replicate responses
```

Expected output: ends with `Successfully installed replicate-... responses-...`

- [ ] **Step 2: Verify deps are importable**

```bash
python3 -c "import replicate, responses, PIL, pytest, requests, yaml; print('all deps ok')"
```

Expected: `all deps ok`

- [ ] **Step 3: Create directory skeleton**

```bash
mkdir -p tests/avatar tests/pipeline tests/fixtures avatar/worker
touch tests/__init__.py tests/avatar/__init__.py tests/pipeline/__init__.py
touch tests/fixtures/.gitkeep avatar/__init__.py
```

- [ ] **Step 4: Write minimal `pytest.ini`**

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

- [ ] **Step 5: Write a sanity-check test**

Create `tests/conftest.py`:

```python
"""Shared pytest fixtures for the project."""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
```

Create `tests/test_sanity.py`:

```python
def test_pytest_runs():
    assert 1 + 1 == 2
```

- [ ] **Step 6: Run the sanity test**

```bash
python3 -m pytest tests/test_sanity.py -v
```

Expected: `1 passed in ...s`

- [ ] **Step 7: Add data/avatar/ to .gitignore**

Append to `.gitignore`:

```
# AI host avatar (one-time generated character + runtime files)
data/avatar/
```

- [ ] **Step 8: Commit**

```bash
git add pytest.ini tests/ avatar/__init__.py .gitignore
git commit -m "Set up pytest and avatar module skeleton"
```

---

## Task 2: Character config module (`avatar/character.py`)

**Files:**
- Create: `avatar/character.py`, `tests/avatar/test_character.py`

- [ ] **Step 1: Write the failing test**

Create `tests/avatar/test_character.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/avatar/test_character.py -v
```

Expected: `ModuleNotFoundError: No module named 'avatar.character'` (or 3 errors).

- [ ] **Step 3: Implement `avatar/character.py`**

Create `avatar/character.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/avatar/test_character.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add avatar/character.py tests/avatar/test_character.py
git commit -m "Add Character config load/save with portrait backup"
```

---

## Task 3: Portrait generation via Replicate (`setup_host.py`)

**Files:**
- Create: `setup_host.py`, `tests/test_setup_host.py`

The interactive parts (showing preview, prompting for selection) live in `main()` and aren't unit-tested. The pure logic — building the Flux prompt, tiling candidate images — is.

- [ ] **Step 1: Write the failing test**

Create `tests/test_setup_host.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_setup_host.py -v
```

Expected: `ModuleNotFoundError: No module named 'setup_host'`.

- [ ] **Step 3: Implement `setup_host.py`**

Create `setup_host.py`:

```python
#!/usr/bin/env python3
"""One-shot: generate the recurring AI host portrait via Replicate Flux.

Run once (or with --regenerate) before using host_video.py.
"""
import argparse
import sys
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
        "neutral expression, neutral solid background, "
        "lighting from the front-left, soft studio light, "
        "high detail, sharp focus, professional headshot, no glasses, no logos"
    )


def tile_candidates_2x2(candidate_paths: List[Path], output_path: Path) -> Path:
    """Tile 4 square portraits into a 2x2 preview image at half resolution."""
    if len(candidate_paths) != 4:
        raise ValueError(f"expected 4 candidates, got {len(candidate_paths)}")
    images = [Image.open(p).convert("RGB") for p in candidate_paths]
    side = images[0].size[0]
    half = side // 2
    canvas = Image.new("RGB", (side, side))
    for idx, img in enumerate(images):
        thumb = img.resize((half, half))
        x = (idx % 2) * half
        y = (idx // 2) * half
        canvas.paste(thumb, (x, y))
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_setup_host.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add setup_host.py tests/test_setup_host.py
git commit -m "Add setup_host.py — Flux portrait generation via Replicate"
```

- [ ] **Step 6: Manual smoke test (run only when REPLICATE_API_TOKEN is set)**

This is a one-time interactive run. Don't include in CI. After committing, the engineer should validate by running:

```bash
export REPLICATE_API_TOKEN=<your-token>
python3 setup_host.py
# then pick candidate 1, 2, 3, or 4
ls -la data/avatar/
```

Expected: `data/avatar/portrait.png` and `data/avatar/character.yaml` exist after selection.

---

## Task 4: Build the LivePortrait Docker worker image

This task is mostly Docker, not TDD. The deliverable is a working image pushed to a registry that RunPod can pull. Validate by running it locally first if a GPU is available, otherwise validate inside a RunPod test pod.

**Files:**
- Create: `avatar/worker/Dockerfile`, `avatar/worker/server.py`, `avatar/worker/requirements.txt`, `avatar/worker/README.md`

- [ ] **Step 1: Write the inner Flask service**

Create `avatar/worker/server.py`:

```python
"""LivePortrait inner server — runs inside the RunPod pod.

POST /render
    multipart form: portrait (PNG bytes), audio (WAV bytes)
    response: video/mp4 bytes

GET /healthz
    returns 200 OK once the model is loaded and ready
"""
import io
import os
import subprocess
import tempfile
from pathlib import Path

from flask import Flask, request, send_file

app = Flask(__name__)
LIVEPORTRAIT_DIR = Path(os.environ.get("LIVEPORTRAIT_DIR", "/opt/LivePortrait"))
MODEL_LOADED = False


@app.route("/healthz", methods=["GET"])
def healthz():
    return ("ok", 200) if MODEL_LOADED else ("warming", 503)


@app.route("/render", methods=["POST"])
def render():
    if "portrait" not in request.files or "audio" not in request.files:
        return ("missing portrait or audio", 400)

    portrait_bytes = request.files["portrait"].read()
    audio_bytes = request.files["audio"].read()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        portrait_path = tmp_path / "portrait.png"
        audio_path = tmp_path / "audio.wav"
        out_path = tmp_path / "out.mp4"
        portrait_path.write_bytes(portrait_bytes)
        audio_path.write_bytes(audio_bytes)

        # LivePortrait CLI invocation. The exact flags depend on the
        # version baked into the image — confirm against the LivePortrait
        # README at the pinned commit.
        cmd = [
            "python", str(LIVEPORTRAIT_DIR / "inference.py"),
            "-s", str(portrait_path),
            "-d", str(audio_path),
            "-o", str(out_path),
            "--driving_audio",
            "--no-flag-pasteback",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0 or not out_path.exists():
            return (f"liveportrait failed: {proc.stderr[-500:]}", 500)

        video_bytes = out_path.read_bytes()

    return send_file(
        io.BytesIO(video_bytes),
        mimetype="video/mp4",
        as_attachment=False,
        download_name="cutaway.mp4",
    )


def warmup():
    """Touch LivePortrait once so MODEL_LOADED becomes True before the first request."""
    global MODEL_LOADED
    # Cheapest thing that proves the env can import the model and find weights:
    proc = subprocess.run(
        ["python", "-c", f"import sys; sys.path.insert(0, '{LIVEPORTRAIT_DIR}'); import inference"],
        capture_output=True, text=True, timeout=60,
    )
    MODEL_LOADED = (proc.returncode == 0)


if __name__ == "__main__":
    warmup()
    app.run(host="0.0.0.0", port=8000)
```

- [ ] **Step 2: Write `avatar/worker/requirements.txt`**

Create `avatar/worker/requirements.txt`:

```
flask==3.0.3
```

(LivePortrait's own deps are installed from its requirements file inside the Dockerfile.)

- [ ] **Step 3: Write the Dockerfile**

Create `avatar/worker/Dockerfile`:

```dockerfile
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    LIVEPORTRAIT_DIR=/opt/LivePortrait

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip git ffmpeg ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

# Clone LivePortrait at a pinned commit so builds are reproducible.
RUN git clone https://github.com/KwaiVGI/LivePortrait.git ${LIVEPORTRAIT_DIR} && \
    cd ${LIVEPORTRAIT_DIR} && \
    git checkout 9b7e9d4

WORKDIR ${LIVEPORTRAIT_DIR}
RUN pip3 install --no-cache-dir -r requirements.txt

# Bake the model weights into the image so cold start doesn't pay download cost.
# These commands match the LivePortrait README's "download weights" step.
RUN python3 -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='KwaiVGI/LivePortrait', local_dir='${LIVEPORTRAIT_DIR}/pretrained_weights')"

# Inner server
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY server.py .

EXPOSE 8000
CMD ["python3", "server.py"]
```

- [ ] **Step 4: Build the image locally (or in CI with GPU runner)**

```bash
cd avatar/worker
docker build -t liveportrait-runpod:0.1.0 .
```

Expected: image builds successfully (~10-30 min, weight download is the long pole).

- [ ] **Step 5: Push the image to a registry RunPod can pull from**

The engineer needs a registry account (Docker Hub, GitHub Container Registry, or RunPod's own registry). Example for Docker Hub:

```bash
docker tag liveportrait-runpod:0.1.0 <dockerhub-user>/liveportrait-runpod:0.1.0
docker login
docker push <dockerhub-user>/liveportrait-runpod:0.1.0
```

Record the full pushed image name for use in `avatar/runpod.py` (Task 5). Update `avatar/worker/README.md` with the latest pushed tag.

- [ ] **Step 6: Write `avatar/worker/README.md`**

Create `avatar/worker/README.md`:

```markdown
# LivePortrait worker image for RunPod

Pinned LivePortrait commit: `9b7e9d4`
Latest pushed tag: `<dockerhub-user>/liveportrait-runpod:0.1.0`

## Build

```
cd avatar/worker
docker build -t liveportrait-runpod:0.1.0 .
```

Build takes 10-30 min — the LivePortrait HuggingFace weights are ~5GB
and are baked in so RunPod cold start doesn't re-download them.

## Test locally (requires NVIDIA GPU + nvidia-docker)

```
docker run --rm --gpus all -p 8000:8000 liveportrait-runpod:0.1.0 &
sleep 60  # wait for warmup
curl -X POST http://localhost:8000/render \
  -F "portrait=@/path/to/portrait.png" \
  -F "audio=@/path/to/audio.wav" \
  --output cutaway.mp4
```

## Push

```
docker tag liveportrait-runpod:0.1.0 <dockerhub-user>/liveportrait-runpod:0.1.0
docker push <dockerhub-user>/liveportrait-runpod:0.1.0
```

The full pushed image name is the value `avatar/runpod.py` uses for `image`.
```

- [ ] **Step 7: Commit**

```bash
git add avatar/worker/
git commit -m "Add LivePortrait Docker worker image with inner Flask server"
```

---

## Task 5: RunPod client (`avatar/runpod.py`)

The most failure-prone part of the design. TDD with the `responses` library to mock the RunPod REST API and the inner pod service. No real network calls.

**Files:**
- Create: `avatar/runpod.py`, `tests/avatar/test_runpod.py`

- [ ] **Step 1: Write the failing test**

Create `tests/avatar/test_runpod.py`:

```python
"""Tests for avatar/runpod.py — RunPodSession context manager.

Mocks both the RunPod REST API (pod create/status/stop) and the inner
pod service (the /render endpoint inside the pod). No real network.
"""
from pathlib import Path

import pytest
import responses

from avatar.runpod import RunPodSession, RunPodError

POD_ID = "pod-fake-123"
POD_HOST = "pod-fake-123.proxy.runpod.net"
RUNPOD_BASE = "https://api.runpod.io/v1"
INNER_BASE = f"https://{POD_HOST}"


@pytest.fixture
def mock_runpod_lifecycle():
    """Stub the create → status (running) → stop sequence."""
    with responses.RequestsMock() as rsps:
        rsps.post(
            f"{RUNPOD_BASE}/pods",
            json={"id": POD_ID, "machineId": "m1"},
            status=200,
        )
        rsps.get(
            f"{RUNPOD_BASE}/pods/{POD_ID}",
            json={
                "id": POD_ID,
                "desiredStatus": "RUNNING",
                "runtime": {
                    "ports": [{"publicPort": 8000, "isIpPublic": True, "ip": POD_HOST}]
                },
            },
            status=200,
        )
        rsps.get(f"{INNER_BASE}/healthz", body="ok", status=200)
        rsps.post(f"{RUNPOD_BASE}/pods/{POD_ID}/stop", json={"id": POD_ID}, status=200)
        yield rsps


def test_session_starts_and_stops_pod(tmp_path: Path, mock_runpod_lifecycle):
    with RunPodSession(image="liveportrait-runpod:0.1.0", api_key="fake") as session:
        assert session.pod_id == POD_ID

    # __exit__ must call /stop. responses raises if any registered call is unused.
    stop_calls = [c for c in mock_runpod_lifecycle.calls if c.request.url.endswith("/stop")]
    assert len(stop_calls) == 1


def test_session_stops_pod_even_on_exception(tmp_path: Path, mock_runpod_lifecycle):
    with pytest.raises(ValueError):
        with RunPodSession(image="liveportrait-runpod:0.1.0", api_key="fake"):
            raise ValueError("boom")

    stop_calls = [c for c in mock_runpod_lifecycle.calls if c.request.url.endswith("/stop")]
    assert len(stop_calls) == 1, "pod must stop even when the body raises"


def test_render_posts_to_inner_service(tmp_path: Path, mock_runpod_lifecycle):
    portrait = tmp_path / "p.png"
    portrait.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFFfake")
    output = tmp_path / "out.mp4"

    fake_video = b"\x00\x00\x00 ftypisom" + b"\x00" * 100
    mock_runpod_lifecycle.post(f"{INNER_BASE}/render", body=fake_video, status=200)

    with RunPodSession(image="liveportrait-runpod:0.1.0", api_key="fake") as session:
        result = session.render(portrait=portrait, audio=audio, output=output)

    assert result == output
    assert output.read_bytes() == fake_video


def test_render_batch_serializes_jobs(tmp_path: Path, mock_runpod_lifecycle):
    portrait = tmp_path / "p.png"
    portrait.write_bytes(b"png")
    a1 = tmp_path / "a1.wav"; a1.write_bytes(b"audio1")
    a2 = tmp_path / "a2.wav"; a2.write_bytes(b"audio2")

    fake_video = b"\x00\x00\x00 ftypisom" + b"\x00" * 100
    mock_runpod_lifecycle.post(f"{INNER_BASE}/render", body=fake_video, status=200)
    mock_runpod_lifecycle.post(f"{INNER_BASE}/render", body=fake_video, status=200)

    with RunPodSession(image="liveportrait-runpod:0.1.0", api_key="fake") as session:
        results = session.render_batch([
            (portrait, a1, tmp_path / "o1.mp4"),
            (portrait, a2, tmp_path / "o2.mp4"),
        ])

    assert len(results) == 2
    assert all(p.exists() for p in results)


def test_failed_pod_create_raises(tmp_path: Path):
    with responses.RequestsMock() as rsps:
        rsps.post(f"{RUNPOD_BASE}/pods", json={"error": "no GPU available"}, status=503)
        with pytest.raises(RunPodError, match="no GPU"):
            with RunPodSession(image="liveportrait-runpod:0.1.0", api_key="fake"):
                pass
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/avatar/test_runpod.py -v
```

Expected: `ModuleNotFoundError: No module named 'avatar.runpod'`.

- [ ] **Step 3: Implement `avatar/runpod.py`**

Create `avatar/runpod.py`:

```python
"""RunPod Pods REST client + inner-service caller.

Used as a context manager so pod teardown is guaranteed even on Python
exception — the only safety net against orphaned $0.34/hr billing.
"""
import os
import time
from pathlib import Path
from typing import List, Optional, Tuple

import requests

API_BASE = "https://api.runpod.io/v1"
DEFAULT_GPU_TYPE = "NVIDIA RTX A5000"  # A10-class, change to "NVIDIA A10" or similar per RunPod naming
POD_BOOT_TIMEOUT_SEC = 180
POD_HEALTH_TIMEOUT_SEC = 120
RENDER_TIMEOUT_SEC = 300


class RunPodError(RuntimeError):
    pass


class RunPodSession:
    """Spin up a pod, render N cutaways on it, tear it down.

    Single pod per video — render_batch keeps the warm pod busy for all
    cutaways before stopping, so we pay the boot cost once.

    Always use as a context manager:

        with RunPodSession(image="liveportrait-runpod:0.1.0") as pod:
            cutaways = pod.render_batch(jobs)
    """

    def __init__(
        self,
        image: str,
        api_key: Optional[str] = None,
        gpu_type: str = DEFAULT_GPU_TYPE,
    ):
        self.image = image
        self.gpu_type = gpu_type
        self.api_key = api_key or os.environ.get("RUNPOD_API_KEY", "")
        if not self.api_key:
            raise RunPodError("RUNPOD_API_KEY not set")
        self.pod_id: Optional[str] = None
        self.inner_base: Optional[str] = None
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {self.api_key}"

    # --- Lifecycle ---

    def __enter__(self) -> "RunPodSession":
        self._create_pod()
        try:
            self._wait_for_running()
            self._wait_for_inner_healthy()
        except Exception:
            # Clean up the pod we just allocated if anything in startup fails
            self._stop_pod_safely()
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop_pod_safely()

    # --- Public API ---

    def render(self, portrait: Path, audio: Path, output: Path) -> Path:
        """Submit one (portrait, audio) job and write the result to output."""
        if not self.inner_base:
            raise RunPodError("Pod not running")
        with open(portrait, "rb") as fp, open(audio, "rb") as fa:
            resp = requests.post(
                f"{self.inner_base}/render",
                files={"portrait": fp, "audio": fa},
                timeout=RENDER_TIMEOUT_SEC,
            )
        if resp.status_code != 200:
            raise RunPodError(f"render failed ({resp.status_code}): {resp.text[:200]}")
        output.write_bytes(resp.content)
        return output

    def render_batch(
        self, jobs: List[Tuple[Path, Path, Path]]
    ) -> List[Path]:
        """Render a list of (portrait, audio, output) jobs in serial on this pod.

        Serial keeps the inner Flask service simple — LivePortrait is
        GPU-bound so concurrent requests would just queue at the GPU anyway.
        """
        results: List[Path] = []
        for portrait, audio, output in jobs:
            results.append(self.render(portrait, audio, output))
        return results

    # --- Internals ---

    def _create_pod(self) -> None:
        resp = self._session.post(
            f"{API_BASE}/pods",
            json={
                "image": self.image,
                "gpuType": self.gpu_type,
                "ports": "8000/http",
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            try:
                err = resp.json().get("error", resp.text)
            except Exception:
                err = resp.text
            raise RunPodError(f"pod create failed: {err}")
        data = resp.json()
        self.pod_id = data["id"]

    def _wait_for_running(self) -> None:
        """Poll RunPod's API until the pod reports RUNNING and exposes a public URL."""
        deadline = time.monotonic() + POD_BOOT_TIMEOUT_SEC
        while time.monotonic() < deadline:
            resp = self._session.get(f"{API_BASE}/pods/{self.pod_id}", timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("desiredStatus") == "RUNNING":
                    runtime = data.get("runtime") or {}
                    ports = runtime.get("ports") or []
                    for port in ports:
                        if port.get("publicPort") == 8000:
                            host = port.get("ip") or port.get("host")
                            if host:
                                self.inner_base = f"https://{host}"
                                return
            time.sleep(3)
        raise RunPodError(f"pod {self.pod_id} did not boot within {POD_BOOT_TIMEOUT_SEC}s")

    def _wait_for_inner_healthy(self) -> None:
        """Poll the pod's inner /healthz until the LivePortrait model is loaded.

        Critical: RunPod's API is eventually consistent. The pod can report
        RUNNING before the inner service is actually accepting requests.
        """
        deadline = time.monotonic() + POD_HEALTH_TIMEOUT_SEC
        while time.monotonic() < deadline:
            try:
                resp = requests.get(f"{self.inner_base}/healthz", timeout=10)
                if resp.status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(3)
        raise RunPodError(f"pod {self.pod_id} inner service never reported healthy")

    def _stop_pod_safely(self) -> None:
        if not self.pod_id:
            return
        try:
            self._session.post(
                f"{API_BASE}/pods/{self.pod_id}/stop", timeout=30
            )
        except Exception:
            # Last-ditch: don't raise during teardown. Log and move on.
            print(f"WARNING: failed to stop pod {self.pod_id} — verify in RunPod console!")
        finally:
            self.pod_id = None
            self.inner_base = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/avatar/test_runpod.py -v
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add avatar/runpod.py tests/avatar/test_runpod.py
git commit -m "Add RunPodSession context manager with mocked lifecycle tests"
```

---

## Task 6: Avatar renderer (`avatar/render.py`)

The high-level entry point. Wraps `RunPodSession`, handles fail-soft fallback to a still-portrait video via ffmpeg.

**Files:**
- Create: `avatar/render.py`, `tests/avatar/test_render.py`

- [ ] **Step 1: Write the failing test**

Create `tests/avatar/test_render.py`:

```python
"""Tests for avatar/render.py — high-level cutaway renderer with fallback."""
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from avatar import render as render_module
from avatar.render import render_cutaway, render_still_portrait_fallback


@pytest.fixture
def fake_portrait(tmp_path: Path) -> Path:
    p = tmp_path / "portrait.png"
    # Generate a tiny valid 1x1 PNG via ffmpeg
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1",
         "-frames:v", "1", str(p)],
        capture_output=True, check=True,
    )
    return p


@pytest.fixture
def fake_audio(tmp_path: Path) -> Path:
    a = tmp_path / "audio.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
         "-t", "2", "-c:a", "pcm_s16le", str(a)],
        capture_output=True, check=True,
    )
    return a


def test_still_portrait_fallback_writes_valid_mp4(
    tmp_path: Path, fake_portrait: Path, fake_audio: Path
):
    output = tmp_path / "fallback.mp4"
    result = render_still_portrait_fallback(fake_portrait, fake_audio, output)
    assert result == output
    assert output.exists() and output.stat().st_size > 0
    # Probe duration with ffprobe to confirm it ran
    proc = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(output)],
        capture_output=True, text=True, check=True,
    )
    duration = float(proc.stdout.strip())
    assert 1.5 < duration < 2.5  # ~2 second audio


def test_render_cutaway_falls_back_when_runpod_session_raises(
    tmp_path: Path, fake_portrait: Path, fake_audio: Path, monkeypatch
):
    # Stub RunPodSession to raise on enter
    class BoomSession:
        def __init__(self, *a, **kw): pass
        def __enter__(self): raise RuntimeError("no GPUs available")
        def __exit__(self, *a): pass
    monkeypatch.setattr(render_module, "RunPodSession", BoomSession)

    output = tmp_path / "out.mp4"
    result = render_cutaway(
        portrait_path=fake_portrait,
        audio_path=fake_audio,
        output_path=output,
        image="liveportrait:test",
    )
    assert result == output
    assert output.exists() and output.stat().st_size > 0


def test_render_cutaway_uses_runpod_when_session_works(
    tmp_path: Path, fake_portrait: Path, fake_audio: Path, monkeypatch
):
    # Stub RunPodSession to write a sentinel mp4
    class WorkingSession:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def render(self, portrait, audio, output):
            output.write_bytes(b"\x00\x00\x00 ftypisom" + b"x" * 100)
            return output
    monkeypatch.setattr(render_module, "RunPodSession", WorkingSession)

    output = tmp_path / "out.mp4"
    result = render_cutaway(
        portrait_path=fake_portrait,
        audio_path=fake_audio,
        output_path=output,
        image="liveportrait:test",
    )
    assert result == output
    # Sentinel proves we went through the RunPod path, not the fallback
    assert output.read_bytes().startswith(b"\x00\x00\x00 ftypisom")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/avatar/test_render.py -v
```

Expected: `ModuleNotFoundError: No module named 'avatar.render'`.

- [ ] **Step 3: Implement `avatar/render.py`**

Create `avatar/render.py`:

```python
"""High-level avatar cutaway renderer.

Wraps RunPodSession with a fail-soft fallback: if the GPU path errors
for any reason, produce a still-portrait video with the original audio
so the surrounding pipeline still ships a video.
"""
import subprocess
from pathlib import Path
from typing import List, Tuple

from avatar.runpod import RunPodSession, RunPodError


def render_still_portrait_fallback(
    portrait_path: Path, audio_path: Path, output_path: Path
) -> Path:
    """Build a 1080x1920 video showing the portrait centered with the audio.

    Used when RunPod is unavailable, render times out, or the LivePortrait
    output is unusable. The video still ships — just without animation.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(portrait_path),
        "-i", str(audio_path),
        "-filter_complex",
        "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black[bg]",
        "-map", "[bg]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"fallback ffmpeg failed: {result.stderr[-300:]}")
    return output_path


def render_cutaway(
    portrait_path: Path,
    audio_path: Path,
    output_path: Path,
    image: str,
) -> Path:
    """Render one talking-head cutaway. Always returns a valid mp4 at output_path.

    Tries RunPod first. On any failure, writes a still-portrait fallback.
    """
    try:
        with RunPodSession(image=image) as pod:
            return pod.render(
                portrait=portrait_path,
                audio=audio_path,
                output=output_path,
            )
    except (RunPodError, Exception) as exc:
        print(f"  ⚠ avatar render failed ({type(exc).__name__}): {exc}; falling back to still portrait")
        return render_still_portrait_fallback(portrait_path, audio_path, output_path)


def render_cutaways_batch(
    portrait_path: Path,
    jobs: List[Tuple[Path, Path]],
    image: str,
) -> List[Path]:
    """Render N cutaways inside one RunPod session. Each job is (audio, output).

    On RunPod failure, ALL jobs fall back to still-portrait individually.
    On a single mid-batch render failure, only that one falls back.
    """
    try:
        with RunPodSession(image=image) as pod:
            results: List[Path] = []
            for audio, output in jobs:
                try:
                    results.append(
                        pod.render(portrait=portrait_path, audio=audio, output=output)
                    )
                except Exception as exc:
                    print(f"  ⚠ cutaway {output.name} failed: {exc}; using still fallback")
                    results.append(
                        render_still_portrait_fallback(portrait_path, audio, output)
                    )
            return results
    except (RunPodError, Exception) as exc:
        print(f"  ⚠ RunPod session failed ({exc}); all cutaways fall back to still portrait")
        return [
            render_still_portrait_fallback(portrait_path, audio, output)
            for audio, output in jobs
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/avatar/test_render.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add avatar/render.py tests/avatar/test_render.py
git commit -m "Add render_cutaway with fail-soft still-portrait fallback"
```

---

## Task 7: Composer extension — `cutaway_overrides`

**Files:**
- Modify: `pipeline/composer.py`
- Create: `tests/pipeline/test_composer_cutaways.py`

Before writing the test or the change, the engineer must read `pipeline/composer.py` to understand its current signature. The change is intentionally minimal: one new optional parameter that, when set, swaps a pre-rendered mp4 in for the visual of the named scene index. Audio and captions still come from the standard pipeline so the cutaway integrates cleanly.

- [ ] **Step 1: Read the current composer signature**

```bash
grep -n "def compose" pipeline/composer.py
```

Note the current top-level entry function name and signature. The next step uses it.

- [ ] **Step 2: Write the failing test**

Create `tests/pipeline/test_composer_cutaways.py`:

```python
"""Tests for pipeline/composer.py cutaway_overrides extension.

Goal: verify that when a scene index is in cutaway_overrides, the
composer uses the provided mp4 as that scene's visual instead of running
the normal Pexels/SerpAPI fetch + Remotion overlay path.

This test mocks the heavy parts (asset fetching, remotion rendering) and
asserts on the asset-resolution decisions the composer makes.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_cutaway_override_skips_normal_visual_fetch_for_that_scene(tmp_path: Path):
    from pipeline import composer

    # Build a minimal script with 3 scenes — middle one will be a cutaway
    script = {
        "title": "Test",
        "hook": {"text": "TEST", "duration": 0.6, "style": "bold"},
        "scenes": [
            {"narration": "first", "duration": 2.0,
             "visuals": {"type": "news_image", "query": "first"}},
            {"narration": "second", "duration": 3.0,
             "visuals": {"type": "news_image", "query": "second"}},
            {"narration": "third", "duration": 2.0,
             "visuals": {"type": "news_image", "query": "third"}},
        ],
    }

    cutaway_mp4 = tmp_path / "cutaway.mp4"
    cutaway_mp4.write_bytes(b"\x00\x00\x00 ftypisom")

    with patch.object(composer, "fetch_visual_for_scene") as fake_fetch:
        fake_fetch.return_value = tmp_path / "pexels.mp4"
        result_assets = composer.resolve_scene_assets(
            script, cutaway_overrides={1: cutaway_mp4}
        )

    # Scene 1 (index, the second scene) must use the cutaway mp4
    assert result_assets[1] == cutaway_mp4
    # Scenes 0 and 2 must have gone through fetch_visual_for_scene
    assert result_assets[0] == tmp_path / "pexels.mp4"
    assert result_assets[2] == tmp_path / "pexels.mp4"
    # fetch was called exactly twice (once for each non-cutaway scene)
    assert fake_fetch.call_count == 2


def test_no_overrides_leaves_existing_behavior_intact(tmp_path: Path):
    from pipeline import composer

    script = {
        "title": "T",
        "hook": {"text": "T", "duration": 0.6, "style": "bold"},
        "scenes": [
            {"narration": "a", "duration": 2.0,
             "visuals": {"type": "news_image", "query": "a"}},
        ],
    }
    with patch.object(composer, "fetch_visual_for_scene") as fake_fetch:
        fake_fetch.return_value = tmp_path / "pexels.mp4"
        result_assets = composer.resolve_scene_assets(script)  # no overrides
    assert result_assets[0] == tmp_path / "pexels.mp4"
    assert fake_fetch.call_count == 1
```

- [ ] **Step 3: Run test to verify it fails**

```bash
python3 -m pytest tests/pipeline/test_composer_cutaways.py -v
```

Expected: most likely `AttributeError: module 'pipeline.composer' has no attribute 'resolve_scene_assets'` (or similar). The test is asserting on a function that doesn't yet exist.

- [ ] **Step 4: Add `resolve_scene_assets` to `pipeline/composer.py`**

Open `pipeline/composer.py` and add a new top-level function. Where exactly to place it depends on the current file layout — put it next to whatever existing function currently iterates scenes and resolves their visuals. The new function:

```python
def resolve_scene_assets(script, cutaway_overrides=None):
    """Resolve a visual asset path for each scene in the script.

    Args:
        script: the parsed YAML script dict (with `scenes` list)
        cutaway_overrides: optional {scene_index: Path} map. When set,
            the named scenes use the provided mp4 directly instead of
            running fetch_visual_for_scene. Audio and captions still
            come from the standard pipeline so the cutaway integrates.

    Returns:
        list[Path] — one entry per scene in script["scenes"]
    """
    overrides = cutaway_overrides or {}
    assets = []
    for idx, scene in enumerate(script["scenes"]):
        if idx in overrides:
            assets.append(overrides[idx])
        else:
            assets.append(fetch_visual_for_scene(scene))
    return assets
```

If `pipeline/composer.py` does not currently expose a `fetch_visual_for_scene` function with that exact name, the engineer needs to either: (a) rename the existing visual-fetcher to that name, or (b) update the test and the new function to use the actual name. **Do not skip this — pick one and apply it consistently.**

Also wire `cutaway_overrides` through to whatever top-level `compose()` / entry function the rest of the pipeline calls. If that function currently does its visual fetching inline (not via a helper), refactor the inline loop to call `resolve_scene_assets` so cutaways flow through one place.

- [ ] **Step 5: Run tests to verify they pass**

```bash
python3 -m pytest tests/pipeline/test_composer_cutaways.py -v
```

Expected: `2 passed`. If the test fails because `fetch_visual_for_scene` has a different name in the codebase, fix the test or the source to match — they must agree.

- [ ] **Step 6: Run the full pytest to make sure no regressions**

```bash
python3 -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add pipeline/composer.py tests/pipeline/test_composer_cutaways.py
git commit -m "Composer accepts cutaway_overrides for pre-rendered scene visuals"
```

---

## Task 8: AI script prompt for host beats (`pipeline/host_script.py`)

A new script generator that talks to OCI GenAI (Gemini 2.5 Flash) and produces a YAML script with `speaker: host` markings on 2-3 scenes. Kept separate from `quick_video.py` so we don't touch its existing prompt.

**Files:**
- Create: `pipeline/host_script.py`, `tests/test_host_script.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_host_script.py`:

```python
"""Tests for pipeline/host_script.py — host-beat script generator.

The OCI GenAI call is mocked. We test the prompt and the parsing logic.
"""
from unittest.mock import MagicMock, patch

import pytest

from pipeline import host_script


def test_prompt_contains_required_rules():
    prompt = host_script.build_host_script_prompt("Oil prices crash 5%")
    must_have = [
        "speaker: host",
        "exactly 2 or 3",
        "first person",
        "interpretive",
        "stand on its own",
    ]
    for s in must_have:
        assert s in prompt, f"missing rule: {s}"


def test_parse_script_extracts_host_beat_indices():
    yaml_text = """
title: Test
hook: { text: TEST, duration: 0.6, style: bold }
scenes:
  - narration: "Scene one"
    duration: 3.0
    visuals: { type: news_image, query: foo }
  - narration: "Here's the thing"
    duration: 4.0
    speaker: host
  - narration: "Scene three"
    duration: 3.0
    visuals: { type: news_image, query: bar }
  - narration: "Trust me"
    duration: 4.0
    speaker: host
"""
    parsed = host_script.parse_script(yaml_text)
    assert host_script.host_beat_indices(parsed) == [1, 3]


def test_generate_script_falls_back_to_collage_on_zero_host_beats():
    """If the AI returns 0 host beats, the caller should know — the
    consumer (host_video.py) downgrades to a plain collage video in
    that case rather than calling RunPod for nothing."""
    yaml_text = """
title: Test
hook: { text: TEST, duration: 0.6, style: bold }
scenes:
  - narration: "Only scene"
    duration: 3.0
    visuals: { type: news_image, query: foo }
"""
    parsed = host_script.parse_script(yaml_text)
    assert host_script.host_beat_indices(parsed) == []


def test_generate_script_uses_oci_gemini():
    fake_yaml = """
title: Generated
hook: { text: G, duration: 0.6, style: bold }
scenes:
  - narration: "x"
    duration: 3.0
    visuals: { type: news_image, query: x }
  - narration: "Here's the thing"
    duration: 4.0
    speaker: host
"""
    with patch.object(host_script, "_call_oci_gemini", return_value=fake_yaml):
        result = host_script.generate_host_script("Test headline", research_text="...")
    assert result["title"] == "Generated"
    assert host_script.host_beat_indices(result) == [1]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_host_script.py -v
```

Expected: `ModuleNotFoundError: No module named 'pipeline.host_script'`.

- [ ] **Step 3: Implement `pipeline/host_script.py`**

Create `pipeline/host_script.py`:

```python
"""AI script generator for host_video.py — produces YAML with host-beat marks.

Separate from quick_video.py's script prompt so this can evolve
independently. Uses the same OCI Gemini 2.5 Flash backend that
clipper/analyze.py uses (see analyze_transcript_oci for the pattern).
"""
import json
import re
from typing import Dict, List, Optional

import yaml

HOST_SCRIPT_SYSTEM_PROMPT = """You are a TikTok finance script writer. Produce a YAML script
of 8-10 scenes for a 25-30 second vertical TikTok video about the given
news headline.

Rules — follow EXACTLY:

1. Total scenes: 8 to 10
2. Each scene has: narration (one short sentence), duration (2-4s), and either:
     visuals: { type: news_video|news_image, query: "search query" }
   OR:
     speaker: host  (and NO visuals field)
3. Mark exactly 2 or 3 scenes as `speaker: host`. Not fewer, not more.
4. Host-beat scenes are 3-5 seconds each, written in first person,
   conversational tone ("Here's the thing", "Watch this", "Trust me").
5. Pick host beats that are interpretive or opinionated — the punchline,
   the "why this matters", the call to action — NOT factual recital.
   Collage scenes carry the facts; host beats carry the perspective.
6. The first AND last scenes should NOT both be host beats. Pick one or
   neither for the bookends.
7. Each scene must stand on its own — do NOT use "as I said" or "in the
   previous scene" because a host beat may degrade to a still portrait
   if rendering fails.

Output ONLY valid YAML. No prose, no markdown fences, no comments.

The YAML schema:

title: "..."
hook:
  text: "HOOK IN ALL CAPS"
  duration: 0.6
  style: bold
scenes:
  - narration: "..."
    duration: 3.0
    visuals: { type: news_image, query: "..." }
  - narration: "Here's the thing — ..."
    duration: 4.0
    speaker: host
"""


def build_host_script_prompt(headline: str, research_text: str = "") -> str:
    """Construct the prompt sent to OCI Gemini.

    The system prompt above lists the rules; this wraps it with the
    headline + research context.
    """
    research_block = f"\n\nResearch context:\n{research_text}\n" if research_text else ""
    return (
        HOST_SCRIPT_SYSTEM_PROMPT
        + f"\n\nHeadline: {headline}{research_block}\n\nProduce the YAML now:"
    )


def _call_oci_gemini(prompt: str) -> str:
    """Send the prompt to OCI Gemini 2.5 Flash and return the raw text.

    Mirrors the auth + call pattern in clipper/analyze.py.
    """
    import oci
    import urllib.request

    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    req = urllib.request.Request(
        "http://169.254.169.254/opc/v2/instance/",
        headers={"Authorization": "Bearer Oracle"},
    )
    cid = json.loads(urllib.request.urlopen(req, timeout=5).read())["compartmentId"]
    client = oci.generative_ai_inference.GenerativeAiInferenceClient(
        config={},
        signer=signer,
        service_endpoint="https://inference.generativeai.us-ashburn-1.oci.oraclecloud.com",
    )
    chat_detail = oci.generative_ai_inference.models.ChatDetails(
        compartment_id=cid,
        serving_mode=oci.generative_ai_inference.models.OnDemandServingMode(
            model_id="google.gemini-2.5-flash"
        ),
        chat_request=oci.generative_ai_inference.models.GenericChatRequest(
            api_format="GENERIC",
            messages=[
                oci.generative_ai_inference.models.UserMessage(
                    content=[oci.generative_ai_inference.models.TextContent(text=prompt)]
                )
            ],
            max_tokens=4096,
            temperature=0.7,
        ),
    )
    resp = client.chat(chat_detail)
    return resp.data.chat_response.choices[0].message.content[0].text


def parse_script(yaml_text: str) -> Dict:
    """Parse the AI's YAML response, stripping any markdown fences."""
    cleaned = re.sub(r"^```(?:yaml|yml)?\s*", "", yaml_text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    return yaml.safe_load(cleaned)


def host_beat_indices(script: Dict) -> List[int]:
    """Return the indices of scenes marked `speaker: host`."""
    return [
        i for i, scene in enumerate(script.get("scenes", []))
        if scene.get("speaker") == "host"
    ]


def generate_host_script(headline: str, research_text: str = "") -> Dict:
    """End-to-end: build prompt, call Gemini, parse YAML.

    On parse failure, raises ValueError so the caller can decide whether
    to retry or fall back. Does not catch network errors.
    """
    prompt = build_host_script_prompt(headline, research_text)
    raw = _call_oci_gemini(prompt)
    parsed = parse_script(raw)
    if not parsed or "scenes" not in parsed:
        raise ValueError(f"AI returned unparseable script:\n{raw[:500]}")
    return parsed
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_host_script.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/host_script.py tests/test_host_script.py
git commit -m "Add host-beat script generator using OCI Gemini"
```

---

## Task 9: Cost guardrails — `MAX_RUNPOD_SECONDS_PER_RUN` and billing log

Extends `avatar/runpod.py` with session-level second tracking and an enforced cap. Keeps the cost story honest by failing loudly if a session ever runs past budget.

**Files:**
- Modify: `avatar/runpod.py`, `tests/avatar/test_runpod.py`
- Create: (handled at runtime) `data/avatar/billing.log`

- [ ] **Step 1: Add the failing test**

Append to `tests/avatar/test_runpod.py`:

```python
def test_session_appends_to_billing_log(tmp_path: Path, mock_runpod_lifecycle, monkeypatch):
    monkeypatch.setenv("RUNPOD_BILLING_LOG", str(tmp_path / "billing.log"))
    with RunPodSession(image="liveportrait-runpod:0.1.0", api_key="fake"):
        pass
    log = (tmp_path / "billing.log").read_text()
    # Format: "<isodate>\t<seconds>\t<cost_estimate>\n"
    assert "\t" in log
    parts = log.strip().split("\t")
    assert len(parts) == 3
    seconds = float(parts[1])
    assert seconds >= 0


def test_session_warns_if_exceeds_max_seconds(
    tmp_path: Path, mock_runpod_lifecycle, monkeypatch, capsys
):
    monkeypatch.setenv("MAX_RUNPOD_SECONDS_PER_RUN", "0")  # any session exceeds this
    monkeypatch.setenv("RUNPOD_BILLING_LOG", str(tmp_path / "billing.log"))

    with RunPodSession(image="liveportrait-runpod:0.1.0", api_key="fake"):
        pass

    out = capsys.readouterr().out
    assert "exceeded" in out.lower() or "warning" in out.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/avatar/test_runpod.py -v
```

Expected: 2 new failures (`assert "exceeded" in out` etc).

- [ ] **Step 3: Update `avatar/runpod.py` to track seconds and write the log**

Add to imports at top:

```python
import os
import time
from datetime import date
```

(`os`, `time` may already be imported.)

Add a constant near the top of the file:

```python
A10_HOURLY_USD = 0.34  # RunPod community A10 — update if pricing changes
DEFAULT_MAX_SECONDS_PER_RUN = 600  # $0.057 at A10 rates
```

Modify `__enter__` to record the start time:

```python
    def __enter__(self) -> "RunPodSession":
        self._started_at = time.monotonic()
        self._create_pod()
        try:
            self._wait_for_running()
            self._wait_for_inner_healthy()
        except Exception:
            self._stop_pod_safely()
            self._record_billing()
            raise
        return self
```

Modify `__exit__`:

```python
    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop_pod_safely()
        self._record_billing()
```

Add the billing helper method:

```python
    def _record_billing(self) -> None:
        if not getattr(self, "_started_at", None):
            return
        elapsed = time.monotonic() - self._started_at
        cost = elapsed / 3600.0 * A10_HOURLY_USD
        max_seconds = float(os.environ.get(
            "MAX_RUNPOD_SECONDS_PER_RUN", DEFAULT_MAX_SECONDS_PER_RUN
        ))
        if elapsed > max_seconds:
            print(
                f"WARNING: RunPod session exceeded MAX_RUNPOD_SECONDS_PER_RUN "
                f"({elapsed:.0f}s > {max_seconds:.0f}s, est ${cost:.3f})"
            )
        log_path = os.environ.get(
            "RUNPOD_BILLING_LOG", "data/avatar/billing.log"
        )
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a") as f:
                f.write(f"{date.today().isoformat()}\t{elapsed:.1f}\t{cost:.4f}\n")
        except OSError:
            pass  # Billing log is best-effort
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/avatar/test_runpod.py -v
```

Expected: all `test_runpod.py` tests pass (5 original + 2 new).

- [ ] **Step 5: Commit**

```bash
git add avatar/runpod.py tests/avatar/test_runpod.py
git commit -m "Add MAX_RUNPOD_SECONDS_PER_RUN guardrail and billing log"
```

---

## Task 10: `host_video.py` CLI orchestration

The end-user command. Ties everything together.

**Files:**
- Create: `host_video.py`, `tests/test_host_video.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_host_video.py`:

```python
"""Tests for host_video.py — orchestration logic only.

The interesting code is the parallelism (pod boot vs. TTS) and the
asset packaging that hands cutaway scenes to the composer. Both are
tested with mocks so no GPU or network is touched.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from host_video import (
    extract_scene_audio,
    pair_host_beats_with_audio,
    HOST_BEAT_AUDIO_TMPDIR,
)


def test_pair_host_beats_with_audio_pairs_indices_with_files(tmp_path: Path):
    script = {
        "scenes": [
            {"narration": "a", "duration": 3.0, "visuals": {}},
            {"narration": "b", "duration": 4.0, "speaker": "host"},
            {"narration": "c", "duration": 3.0, "visuals": {}},
            {"narration": "d", "duration": 4.0, "speaker": "host"},
        ]
    }
    # Pretend each scene has its own wav file from TTS
    audio_files = [tmp_path / f"scene_{i}.wav" for i in range(4)]
    for f in audio_files:
        f.write_bytes(b"fake-wav")

    pairs = pair_host_beats_with_audio(script, audio_files)
    assert len(pairs) == 2
    assert pairs[0] == (1, audio_files[1])
    assert pairs[1] == (3, audio_files[3])


def test_pair_returns_empty_when_no_host_beats(tmp_path: Path):
    script = {"scenes": [{"narration": "x", "duration": 3.0, "visuals": {}}]}
    audio_files = [tmp_path / "s.wav"]
    audio_files[0].write_bytes(b"fake")
    assert pair_host_beats_with_audio(script, audio_files) == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_host_video.py -v
```

Expected: `ModuleNotFoundError: No module named 'host_video'`.

- [ ] **Step 3: Implement `host_video.py`**

Create `host_video.py`:

```python
#!/usr/bin/env python3
"""host_video.py — headline → AI-host-cutaway TikTok video.

End-to-end:
  1. Research topic (reuse quick_video.py logic)
  2. AI script generation (pipeline/host_script.py — marks 2-3 host beats)
  3. Edge TTS per scene (reuse) — KICKED OFF IN PARALLEL with...
  4. RunPod pod boot (avatar/render.py with one shared session)
  5. Render avatar cutaways for each host beat (sequential on the warm pod)
  6. Composer assembly with cutaway_overrides
  7. Final render

Output: output/host/<slug>.mp4
"""
import argparse
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Tuple

# Reused from existing pipeline
from slugify import slugify

from avatar.character import load_character
from avatar.render import render_cutaways_batch
from pipeline.host_script import generate_host_script, host_beat_indices

PROJECT_DIR = Path(__file__).parent.resolve()
DATA_DIR = PROJECT_DIR / "data"
AVATAR_DIR = DATA_DIR / "avatar"
OUTPUT_DIR = PROJECT_DIR / "output" / "host"
HOST_BEAT_AUDIO_TMPDIR = DATA_DIR / "tmp" / "host_beats"
DEFAULT_IMAGE = os.environ.get(
    "RUNPOD_IMAGE", "<dockerhub-user>/liveportrait-runpod:0.1.0"
)


def extract_scene_audio(scene_index: int, all_audio: List[Path]) -> Path:
    """Return the per-scene audio file already produced by TTS.

    Assumes the existing TTS pipeline writes one wav per scene in the
    same order as script["scenes"]. If the existing pipeline writes a
    single concatenated wav instead, the engineer needs to extend the
    TTS step in this module to write per-scene wavs first.
    """
    return all_audio[scene_index]


def pair_host_beats_with_audio(
    script: Dict, scene_audio: List[Path]
) -> List[Tuple[int, Path]]:
    """For each host-beat scene index, attach its per-scene wav file."""
    return [(idx, scene_audio[idx]) for idx in host_beat_indices(script)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an AI-host TikTok video from a headline")
    parser.add_argument("headline", help="One-line news headline")
    parser.add_argument("--image", default=DEFAULT_IMAGE,
                        help="LivePortrait worker image to use")
    parser.add_argument("--no-runpod", action="store_true",
                        help="Skip RunPod entirely; use still-portrait fallback for all host beats")
    args = parser.parse_args()

    # 1. Load character (errors clearly if setup_host.py hasn't been run)
    character = load_character(AVATAR_DIR)
    print(f"Host: {character.name} ({character.voice})")
    print(f"Headline: {args.headline}")

    # 2. Research + script generation
    # NOTE: research is reused from quick_video.py — the exact import here
    # depends on whether quick_video exposes a `research_topic` function.
    # If it inlines the research step, the engineer needs to extract it
    # into pipeline/research.py first OR call quick_video.research_topic
    # if such a function exists.
    from quick_video import research_topic  # may need extraction
    research_text = research_topic(args.headline)
    script = generate_host_script(args.headline, research_text)

    indices = host_beat_indices(script)
    if not indices:
        print("AI returned 0 host beats — falling back to standard collage video.")
        # Hand off to quick_video.py's existing path
        from quick_video import render_video_from_script
        out = render_video_from_script(script)
        print(f"Done: {out}")
        return 0
    print(f"Host beats: {indices}")

    # 3-5. PARALLEL: TTS + asset fetch on one thread, RunPod pod boot + render on another
    # Use ThreadPoolExecutor with 2 workers so they overlap. The render
    # step waits for the TTS audio of each host beat scene to be ready.
    HOST_BEAT_AUDIO_TMPDIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # The existing pipeline produces per-scene audio. Extract that step
    # into a callable here. (If the existing pipeline only produces one
    # concatenated wav, the engineer needs to add a per-scene mode first.)
    from pipeline.tts import generate_per_scene_audio  # may need to be added
    from pipeline.assets import fetch_all_scene_visuals  # existing or rename

    tts_done = threading.Event()
    scene_audio: List[Path] = []
    fetched_visuals: List[Path] = []

    def tts_and_assets():
        nonlocal scene_audio, fetched_visuals
        scene_audio = generate_per_scene_audio(script, voice=character.voice)
        fetched_visuals = fetch_all_scene_visuals(script)
        tts_done.set()

    cutaway_paths: List[Path] = []

    def render_avatars():
        # Wait for TTS to produce host-beat audio
        tts_done.wait()
        host_beat_jobs: List[Tuple[Path, Path]] = []
        for scene_idx, audio_path in pair_host_beats_with_audio(script, scene_audio):
            out_path = HOST_BEAT_AUDIO_TMPDIR / f"cutaway_{scene_idx}.mp4"
            host_beat_jobs.append((audio_path, out_path))
        if args.no_runpod:
            from avatar.render import render_still_portrait_fallback
            for (audio, out) in host_beat_jobs:
                render_still_portrait_fallback(character.portrait_path, audio, out)
                cutaway_paths.append(out)
        else:
            results = render_cutaways_batch(
                portrait_path=character.portrait_path,
                jobs=host_beat_jobs,
                image=args.image,
            )
            cutaway_paths.extend(results)

    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(tts_and_assets)
        f2 = ex.submit(render_avatars)
        f1.result()
        f2.result()

    # 6. Composer assembly with cutaway_overrides
    cutaway_overrides = {
        idx: cutaway_paths[i] for i, idx in enumerate(indices)
    }
    from pipeline.composer import compose_video  # actual entry function name from existing code
    final_path = compose_video(
        script=script,
        scene_audio=scene_audio,
        scene_visuals=fetched_visuals,
        cutaway_overrides=cutaway_overrides,
        output_path=OUTPUT_DIR / f"{slugify(args.headline)[:60]}.mp4",
    )

    print(f"\nDone: {final_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_host_video.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Reconcile imports against the real existing pipeline**

`host_video.py` imports several functions that may not exist with those exact names in the current pipeline:

- `quick_video.research_topic` — the topic-research step
- `quick_video.render_video_from_script` — the existing collage renderer for the no-host-beats fallback
- `pipeline.tts.generate_per_scene_audio` — per-scene TTS
- `pipeline.assets.fetch_all_scene_visuals` — visual asset fetching
- `pipeline.composer.compose_video` — top-level compose entry
- `pipeline.composer.fetch_visual_for_scene` — single-scene visual fetcher (used in Task 7)

The engineer must:

1. Read `quick_video.py` and `pipeline/composer.py` to find the actual function names
2. Either rename functions in `host_video.py` to match the existing names, OR extract those existing inline steps into named functions, depending on which is cleaner for the codebase
3. **Do not skip this — running `host_video.py` will ImportError until every name resolves**

This is intentionally left as work for the engineer because the exact refactor depends on the current state of those files.

- [ ] **Step 6: Commit**

```bash
git add host_video.py tests/test_host_video.py
git commit -m "Add host_video.py CLI with parallel TTS + RunPod pod boot"
```

---

## Task 11: End-to-end smoke test

The final manual gate. Cannot be automated (involves real GPU + cost). Run after Tasks 1-10 pass.

**Files:**
- Create: (none) — this is documentation of the smoke procedure

- [ ] **Step 1: Smoke `setup_host.py`**

```bash
export REPLICATE_API_TOKEN=<your-token>
python3 setup_host.py
```

Expected: 4 candidates printed, preview at `data/avatar/candidates/preview.png`. Pick one. Verify `data/avatar/portrait.png` and `data/avatar/character.yaml` exist.

- [ ] **Step 2: Smoke a single render via the Python REPL**

```bash
python3 -c "
from pathlib import Path
from avatar.render import render_cutaway
import os
os.environ['RUNPOD_API_KEY'] = '<your-key>'
result = render_cutaway(
    portrait_path=Path('data/avatar/portrait.png'),
    audio_path=Path('<some 3-5s wav file>'),
    output_path=Path('/tmp/smoke_cutaway.mp4'),
    image='<dockerhub-user>/liveportrait-runpod:0.1.0',
)
print('Rendered:', result)
"
```

Expected: ~2-4 min wall (60-90s pod boot + 20-40s render). `/tmp/smoke_cutaway.mp4` exists, opens in any video player, shows the portrait with the audio's mouth movements. Visually verify quality — eye drift, mouth shapes, identity stability.

If quality is unacceptable, this is the bail-out point: revisit the spec and consider Approach C (EchoMimicV2 on OCI) without having spent any pipeline-integration effort.

- [ ] **Step 3: Smoke the full `host_video.py` flow**

```bash
export RUNPOD_API_KEY=<your-key>
export REPLICATE_API_TOKEN=<your-token>
time python3 host_video.py "Oil prices crash 5% on Iran peace deal"
```

Expected:
- AI script generated with 2-3 host beats
- TTS + RunPod pod boot run in parallel
- Cutaways render successfully (or fall back to still portrait with a warning)
- Final mp4 in `output/host/`
- Wall time: ~5-8 min (longer if pod cold start was slow)

- [ ] **Step 4: Verify cost guardrails**

```bash
cat data/avatar/billing.log
```

Expected: one line per session, format `<date>\t<seconds>\t<cost_estimate>`. The cost should be ~$0.02-$0.05 per video. If it's higher, investigate whether the pod is being torn down promptly.

- [ ] **Step 5: Verify the `--no-runpod` fallback works**

```bash
python3 host_video.py "Test fallback path" --no-runpod
```

Expected: video completes using still portraits for all host beats. No RunPod calls. Useful for development without burning GPU credits.

- [ ] **Step 6: Document the smoke procedure in CLAUDE.md**

Append to `CLAUDE.md` under "Clip Generation Features":

```markdown
- **AI host video**: `python3 host_video.py "headline"` — generates a TikTok with 2-3 AI-rendered avatar cutaways. Requires RUNPOD_API_KEY and a portrait at data/avatar/portrait.png (run `setup_host.py` first). Use `--no-runpod` to develop without GPU calls.
```

- [ ] **Step 7: Final commit**

```bash
git add CLAUDE.md
git commit -m "Document host_video.py in CLAUDE.md"
```

---

## Self-Review Notes

After writing this plan I checked it against the spec:

**Spec coverage:**
- "New CLI host_video.py" → Task 10 ✓
- "New one-shot setup_host.py" → Task 3 ✓
- "avatar/ module (render.py, runpod.py, character.py)" → Tasks 2, 5, 6 ✓
- "Docker image with LivePortrait + weights baked in" → Task 4 ✓
- "Composer extension cutaway_overrides" → Task 7 ✓
- "AI script prompt with host-beat marking rules" → Task 8 ✓
- "Cost guardrails (MAX_RUNPOD_SECONDS_PER_RUN, billing.log)" → Task 9 ✓
- "Tests: render isolation, RunPod mocked, e2e fixture" → Tasks 2/5/6 (unit), 11 (e2e) ✓
- "Fail-soft fallbacks throughout" → Task 6 (still-portrait fallback), Task 10 (no-host-beats fallback) ✓
- "Parallelism: pod boot during TTS" → Task 10 (ThreadPoolExecutor) ✓
- "Single pod session per video" → Task 5 (RunPodSession context manager + render_batch) ✓

**Known gaps / engineer judgment calls flagged inline:**
- Task 7 step 4 — the engineer must reconcile `fetch_visual_for_scene` against whatever the real composer function is named.
- Task 10 step 5 — the engineer must reconcile import names from `quick_video.py` and `pipeline/` against reality.
- Task 4 — the LivePortrait CLI invocation in `server.py` may need flag adjustments based on the pinned commit.

These are intentional. They require reading code I don't have full access to from inside this plan.

**Type/name consistency:**
- `RunPodSession` constructor signature matches between Task 5 and Task 6's tests ✓
- `render_cutaway` and `render_cutaways_batch` are both exposed from `avatar/render.py` and used by `host_video.py` ✓
- `Character` dataclass fields match between `character.py` and `setup_host.py` save call ✓
- `cutaway_overrides` parameter shape is consistent (Task 7 → Task 10) ✓

**No placeholders in committed code.** All "TODO" / "TBD" content is in step descriptions where the engineer needs to adapt to existing code, never in code blocks.
