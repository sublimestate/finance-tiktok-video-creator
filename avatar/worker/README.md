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
