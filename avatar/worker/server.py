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
from functools import wraps
from pathlib import Path

from flask import Flask, request, send_file

app = Flask(__name__)
LIVEPORTRAIT_DIR = Path(os.environ.get("LIVEPORTRAIT_DIR", "/opt/LivePortrait"))
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
        try:
            proc = subprocess.run(cmd, capture_output=True, text=False, timeout=300)
        except subprocess.TimeoutExpired:
            return ("liveportrait timed out after 300s", 504)
        if proc.returncode != 0 or not out_path.exists():
            stderr_text = proc.stderr.decode('utf-8', errors='replace') if proc.stderr else ''
            return (f"liveportrait failed: {stderr_text[-2000:]}", 500)

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
