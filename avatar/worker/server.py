"""MuseTalk inner server — runs inside the RunPod pod.

POST /render
    multipart form: portrait (PNG bytes), audio (WAV bytes)
    response: video/mp4 bytes

GET /healthz
    returns 200 OK once MuseTalk is importable (weights are baked into
    the image, so loading is effectively instant after the first /render)
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
from functools import wraps
from pathlib import Path

from flask import Flask, request, send_file

app = Flask(__name__)
MUSETALK_DIR = Path(os.environ.get("MUSETALK_DIR", "/opt/MuseTalk"))
MODEL_LOADED = False

# Optional shared-secret auth. Set WORKER_AUTH_TOKEN in the RunPod pod env to
# enable. When unset the check is skipped so local docker-run dev flow works.
_AUTH_TOKEN = os.environ.get("WORKER_AUTH_TOKEN", "").strip()


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if _AUTH_TOKEN:
            token = request.headers.get("X-Worker-Token", "")
            if token != _AUTH_TOKEN:
                return ("unauthorized", 401)
        return f(*args, **kwargs)
    return decorated


@app.route("/healthz", methods=["GET"])
@require_auth
def healthz():
    return ("ok", 200) if MODEL_LOADED else ("warming", 503)


@app.route("/render", methods=["POST"])
@require_auth
def render():
    if "portrait" not in request.files or "audio" not in request.files:
        return ("missing portrait or audio", 400)

    portrait_bytes = request.files["portrait"].read()
    audio_bytes = request.files["audio"].read()

    with tempfile.TemporaryDirectory(dir=str(MUSETALK_DIR)) as tmp:
        tmp_path = Path(tmp)
        portrait_path = tmp_path / "portrait.png"
        audio_path = tmp_path / "audio.wav"
        config_path = tmp_path / "config.yaml"
        result_dir = tmp_path / "results"

        portrait_path.write_bytes(portrait_bytes)
        audio_path.write_bytes(audio_bytes)

        # MuseTalk reads a YAML config describing tasks. video_path can
        # be an image (jpg/png) — MuseTalk treats it as a single-frame
        # source and extends it to match audio duration.
        config_path.write_text(
            f"task_0:\n"
            f" video_path: \"{portrait_path}\"\n"
            f" audio_path: \"{audio_path}\"\n"
        )

        cmd = [
            sys.executable, "-m", "scripts.inference",
            "--inference_config", str(config_path),
            "--result_dir", str(result_dir),
            "--unet_model_path", str(MUSETALK_DIR / "models/musetalkV15/unet.pth"),
            "--unet_config", str(MUSETALK_DIR / "models/musetalkV15/musetalk.json"),
            "--whisper_dir", str(MUSETALK_DIR / "models/whisper"),
            "--version", "v15",
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=False,
                timeout=300,
                cwd=str(MUSETALK_DIR),
            )
        except subprocess.TimeoutExpired:
            return ("musetalk timed out after 300s", 504)

        # MuseTalk's inference.py has a non-fatal cleanup bug
        # (NameError on save_dir_full) that fires AFTER the output mp4
        # is written. Don't trust returncode — check whether the file
        # actually exists.
        outputs = list(result_dir.glob("v15/*.mp4"))
        # Filter out intermediate temp files
        outputs = [p for p in outputs if not p.name.startswith("temp_")]

        if not outputs:
            stderr_text = (
                proc.stderr.decode("utf-8", errors="replace")
                if proc.stderr
                else ""
            )
            return (
                f"musetalk produced no output: {stderr_text[-2000:]}",
                500,
            )

        video_bytes = outputs[0].read_bytes()

    return send_file(
        io.BytesIO(video_bytes),
        mimetype="video/mp4",
        as_attachment=False,
        download_name="cutaway.mp4",
    )


def warmup():
    """Verify the MuseTalk inference module is importable.

    MuseTalk loads weights lazily on the first inference call, so there
    is no "model loaded" state to warm up. We just confirm that the
    Python env + code + deps are all in place.
    """
    global MODEL_LOADED
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, '.'); import scripts.inference",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(MUSETALK_DIR),
    )
    MODEL_LOADED = proc.returncode == 0


if __name__ == "__main__":
    warmup()
    app.run(host="0.0.0.0", port=8000)
