"""EchoMimic V1 talking-head generation on Modal.

Single-pass: portrait image + audio → talking-head video.
Apache 2.0 license, tested on V100 16GB → fits A10G 24GB comfortably.
"""
import modal

app = modal.App("echomimic-v1")

# Persistent volume for the model weights so we don't re-download on
# every cold start.
weights_vol = modal.Volume.from_name("echomimic-weights", create_if_missing=True)

WEIGHTS_DIR = "/weights"

# Image: PyTorch + EchoMimic deps + git clone the repo into /opt/EchoMimic
image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0")
    .pip_install(
        "torch==2.0.1",
        "torchvision==0.15.2",
        "torchaudio==2.0.2",
        index_url="https://download.pytorch.org/whl/cu118",
    )
    .pip_install(
        # EchoMimic's requirements.txt
        "diffusers==0.24.0",
        "transformers==4.36.2",
        "accelerate==0.26.1",
        "einops==0.4.1",
        "omegaconf==2.2.3",
        "av==13.0.0",
        "decord==0.6.0",
        "imageio==2.33.0",
        "imageio-ffmpeg==0.4.9",
        "librosa==0.10.1",
        "moviepy==1.0.3",
        "numpy==1.23.5",
        "opencv-python==4.9.0.80",
        "Pillow==10.1.0",
        "scikit-image==0.22.0",
        "scipy==1.11.4",
        "soundfile==0.12.1",
        "tqdm==4.66.1",
        "facenet-pytorch==2.5.3",
        "huggingface_hub==0.20.3",  # diffusers 0.24 needs cached_download (gone in >=0.26)
        "mediapipe",
        "pydub",
        "ffmpeg-python",
        "openai-whisper",
    )
    .run_commands(
        "git clone https://github.com/BadToBest/EchoMimic.git /opt/EchoMimic",
        # EchoMimic bug: xyxy is a Python list slice, np.round needs a real array
        "sed -i 's|xyxy = np.round(xyxy)|xyxy = np.round(np.asarray(xyxy, dtype=np.float64))|' /opt/EchoMimic/infer_audio2vid.py",
    )
)


@app.function(
    image=image,
    gpu="A10G",
    timeout=900,
    volumes={WEIGHTS_DIR: weights_vol},
)
def download_weights(force: bool = False) -> str:
    """One-shot: pull the EchoMimic weights into the persistent volume.

    Uses local_dir_use_symlinks=False so files are copied into the
    Modal volume directly. Otherwise HuggingFace symlinks to a local
    cache outside the volume and Modal commits dangling symlinks.
    """
    import os
    import shutil
    from huggingface_hub import snapshot_download

    target = os.path.join(WEIGHTS_DIR, "echomimic")
    sentinel = os.path.join(target, "denoising_unet.pth")
    if (
        os.path.exists(sentinel)
        and os.path.getsize(sentinel) > 1_000_000_000
        and not force
    ):
        return f"already downloaded: {target}"
    if os.path.exists(target):
        shutil.rmtree(target)

    snapshot_download(
        repo_id="BadToBest/EchoMimic",
        local_dir=target,
        local_dir_use_symlinks=False,
        allow_patterns=[
            "denoising_unet.pth",
            "reference_unet.pth",
            "face_locator.pth",
            "motion_module.pth",
            "audio_processor/*",
            "sd-image-variations-diffusers/**",
            "sd-vae-ft-mse/**",
        ],
    )
    weights_vol.commit()
    return f"downloaded to: {target}"


@app.function(
    image=image,
    timeout=120,
    volumes={WEIGHTS_DIR: weights_vol},
)
def list_weights() -> str:
    """Debug: list what's actually in the weights volume."""
    import os
    weights_vol.reload()
    out = []
    for root, _dirs, files in os.walk(WEIGHTS_DIR):
        for f in files:
            p = os.path.join(root, f)
            try:
                size = os.path.getsize(p)
                out.append(f"{size/1e6:.1f}MB  {p}")
            except OSError as e:
                out.append(f"BROKEN  {p}  {e}")
    result = "\n".join(out[:80]) if out else "(empty)"
    print(result)
    return result


@app.function(
    image=image,
    gpu="A10G",
    timeout=1800,
    volumes={WEIGHTS_DIR: weights_vol},
)
def render(portrait_bytes: bytes, audio_bytes: bytes) -> bytes:
    """Render a talking-head video from a portrait image + audio.

    Returns the raw mp4 bytes. The caller writes them to disk.
    """
    import os
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    weights_vol.reload()  # pick up any changes from download_weights
    weights_root = Path(WEIGHTS_DIR) / "echomimic"
    if not (weights_root / "denoising_unet.pth").exists():
        raise RuntimeError(
            "EchoMimic weights not in volume. Run download_weights first."
        )

    # Symlink the weights into the EchoMimic repo where the config expects
    repo = Path("/opt/EchoMimic")
    weights_link = repo / "pretrained_weights"
    if weights_link.exists() and not weights_link.is_symlink():
        shutil.rmtree(weights_link)
    if not weights_link.exists():
        weights_link.symlink_to(weights_root)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        portrait_path = tmp_path / "portrait.png"
        audio_path = tmp_path / "audio.wav"
        portrait_path.write_bytes(portrait_bytes)
        audio_path.write_bytes(audio_bytes)

        # Build a minimal config the audio2vid script will read.
        # EchoMimic's animation.yaml shape: ref_images, audios, lengths, etc.
        config_path = tmp_path / "animation.yaml"
        config_path.write_text(
            f"""## dependency models (relative to repo root)
pretrained_base_model_path: "./pretrained_weights/sd-image-variations-diffusers/"
pretrained_vae_path: "./pretrained_weights/sd-vae-ft-mse/"
audio_model_path: "./pretrained_weights/audio_processor/whisper_tiny.pt"

## echo mimic checkpoint
denoising_unet_path: "./pretrained_weights/denoising_unet.pth"
reference_unet_path: "./pretrained_weights/reference_unet.pth"
face_locator_path: "./pretrained_weights/face_locator.pth"
motion_module_path: "./pretrained_weights/motion_module.pth"

## inference config + dtype
inference_config: "./configs/inference/inference_v2.yaml"
weight_dtype: 'fp16'

## render params
W: 512
H: 512
L: 240
seed: 420
facemusk_dilation_ratio: 0.1
facecrop_dilation_ratio: 0.5
context_frames: 12
context_overlap: 3
cfg: 2.5
steps: 30
sample_rate: 16000
fps: 24
device: "cuda"

## test cases
test_cases:
  "{portrait_path}":
    - "{audio_path}"
"""
        )

        # Run inference. EchoMimic writes outputs to ./output by default.
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo)
        proc = subprocess.run(
            ["python", "-u", "infer_audio2vid.py", "--config", str(config_path)],
            cwd=str(repo),
            env=env,
            capture_output=True,
            text=False,
            timeout=1700,
        )
        # Find the output mp4
        candidates = list((repo / "output").rglob("*.mp4"))
        if not candidates:
            stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
            stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
            raise RuntimeError(
                f"echomimic produced no output\n"
                f"---STDOUT---\n{stdout[-1500:]}\n"
                f"---STDERR---\n{stderr[-1500:]}"
            )
        # Pick the most recent
        out = max(candidates, key=lambda p: p.stat().st_mtime)
        return out.read_bytes()


@app.local_entrypoint()
def main(portrait: str, audio: str, output: str = "/tmp/echomimic_out.mp4"):
    """Local entrypoint for running a one-off render."""
    portrait_bytes = open(portrait, "rb").read()
    audio_bytes = open(audio, "rb").read()
    print(f"calling render with portrait={portrait} audio={audio}")
    result = render.remote(portrait_bytes, audio_bytes)
    open(output, "wb").write(result)
    print(f"wrote {output} ({len(result)} bytes)")
