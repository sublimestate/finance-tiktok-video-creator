# MuseTalk worker image for RunPod

MuseTalk version: v1.5 (unet.pth, WHISPER + SD VAE + DWPose + LatentSync + face-parse-bisent weights all baked in)
Source repo: https://github.com/TMElyralab/MuseTalk
Latest pushed tag: `<dockerhub-user>/musetalk-runpod:0.1.0`

## Why MuseTalk and not LivePortrait

The original plan used LivePortrait, which turned out to be a **video-driven** expression-transfer model, not audio-driven. On validation against a real Tesla T4, we swapped to **MuseTalk** — a Tencent lip-sync model that does accept `(portrait_image, audio_wav) → talking_video.mp4`, fits comfortably in 16 GB VRAM, and runs ~2 minutes for 8 seconds of audio on a T4.

The trade-off: MuseTalk keeps head pose static and only animates the mouth region. For 3–5 second cutaways in a fast-cut TikTok this reads as fine. If richer head motion is needed later, EchoMimicV2 or Hallo2 are drop-in replacements that need an A100.

## Build

```
cd avatar/worker
docker build -t musetalk-runpod:0.1.0 .
```

Build takes 20–40 min — the baked model weights are ~6 GB total (MuseTalk V1.5 unet, SD VAE, Whisper tiny, DWPose, LatentSync SyncNet, face parsing, s3fd face detection).

## Test locally (requires NVIDIA GPU + nvidia-docker)

```
docker run --rm --gpus all -p 8000:8000 musetalk-runpod:0.1.0 &
sleep 30  # wait for warmup
curl -X POST http://localhost:8000/render \
  -F "portrait=@/path/to/portrait.png" \
  -F "audio=@/path/to/audio.wav" \
  --output cutaway.mp4
```

## Push

```
docker tag musetalk-runpod:0.1.0 <dockerhub-user>/musetalk-runpod:0.1.0
docker push <dockerhub-user>/musetalk-runpod:0.1.0
```

The full pushed image name is the value `host_video.py` uses for `RUNPOD_IMAGE` and that `avatar/runpod.py` receives as `image=`.

## Authentication

The worker supports an optional shared-secret header to prevent unauthorized
use of the public RunPod HTTPS proxy URL.

**Set on the pod (RunPod env vars):**
```
WORKER_AUTH_TOKEN=<random secret>
```

**Pass from the caller on every request:**
```
X-Worker-Token: <same secret>
```

Both `/render` and `/healthz` require the header when `WORKER_AUTH_TOKEN` is
set. A missing or wrong token returns HTTP 401.

When `WORKER_AUTH_TOKEN` is empty or unset the check is skipped entirely, so
the local `docker run` dev workflow above works without any changes.

## Known non-fatal issue

MuseTalk's `scripts/inference.py` has a cleanup bug where `save_dir_full` is referenced before assignment. This fires AFTER the output mp4 is already written. The server checks for the output file's existence rather than trusting the subprocess exit code, so the error is silently absorbed.
