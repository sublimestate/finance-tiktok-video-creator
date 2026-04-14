"""Transcribe a specific clip segment for accurate caption timing."""

import json
import os
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from typing import List, Dict

from vosk import Model, KaldiRecognizer

# Cache vosk models — large for clip captions, small for full-video transcription.
# The lock prevents a race when multiple parallel prep threads hit a cold cache
# and each try to load the 1.8GB large model simultaneously.
_LARGE_MODEL_PATH = str(Path(__file__).parent.parent / "data" / "models" / "vosk-model-en-us-0.22")
_SMALL_MODEL_PATH = str(Path(__file__).parent.parent / "data" / "models" / "vosk-model-small-en-us-0.15")
_models = {}
_model_lock = threading.Lock()


def _get_model(size: str = "large") -> Model:
    """Get a cached Vosk model. size: 'large' (accurate) or 'small' (fast)."""
    if size in _models:
        return _models[size]

    with _model_lock:
        # Re-check under the lock in case another thread loaded it while we waited
        if size in _models:
            return _models[size]

        if size == "large" and os.path.exists(_LARGE_MODEL_PATH):
            _models[size] = Model(_LARGE_MODEL_PATH)
        elif os.path.exists(_SMALL_MODEL_PATH):
            _models[size] = Model(_SMALL_MODEL_PATH)
        else:
            return None

        return _models[size]


def transcribe_clip(video_path: str, start_time: float, end_time: float) -> List[Dict]:
    """Transcribe a video segment using the small model (fast, for AI analysis).

    Returns list of {"start": float, "end": float, "text": str} with
    timestamps relative to clip start (0-based).
    """
    model = _get_model("small")
    if model is None:
        return []

    # Extract audio for this segment
    tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_wav.close()

    try:
        duration = end_time - start_time
        extract_timeout = max(60, int(duration / 10))
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(start_time), "-i", video_path,
             "-t", str(duration),
             "-ar", "16000", "-ac", "1", "-f", "wav", tmp_wav.name],
            capture_output=True, timeout=extract_timeout,
        )

        rec = KaldiRecognizer(model, 16000)
        rec.SetWords(True)

        wf = wave.open(tmp_wav.name, "rb")
        all_words = []

        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                for w in result.get("result", []):
                    all_words.append(w)

        # Final result
        final = json.loads(rec.FinalResult())
        for w in final.get("result", []):
            all_words.append(w)

        wf.close()

        # Build small segments from individual words (3-5 words per segment)
        # This gives much tighter timing than vosk's default long segments
        segments = []
        words_per_seg = 4
        for i in range(0, len(all_words), words_per_seg):
            group = all_words[i:i + words_per_seg]
            if group:
                text = " ".join(w["word"] for w in group)
                segments.append({
                    "start": group[0]["start"],
                    "end": group[-1]["end"],
                    "text": text,
                })

        return segments

    finally:
        if os.path.exists(tmp_wav.name):
            os.unlink(tmp_wav.name)


def transcribe_clip_words(video_path: str, start_time: float, end_time: float) -> List[Dict]:
    """Transcribe a clip with the large model for accurate per-word timestamps.

    Returns list of {"word": str, "start": float, "end": float} with
    timestamps relative to clip start (0-based).
    """
    model = _get_model("large")
    if model is None:
        return []

    tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_wav.close()

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(start_time), "-i", video_path,
             "-t", str(end_time - start_time),
             "-ar", "16000", "-ac", "1", "-f", "wav", tmp_wav.name],
            capture_output=True, timeout=30,
        )

        rec = KaldiRecognizer(model, 16000)
        rec.SetWords(True)

        wf = wave.open(tmp_wav.name, "rb")
        all_words = []

        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                for w in result.get("result", []):
                    all_words.append({
                        "word": w["word"],
                        "start": w["start"],
                        "end": w["end"],
                    })

        final = json.loads(rec.FinalResult())
        for w in final.get("result", []):
            all_words.append({
                "word": w["word"],
                "start": w["start"],
                "end": w["end"],
            })

        wf.close()
        return all_words

    except Exception:
        return []
    finally:
        if os.path.exists(tmp_wav.name):
            os.unlink(tmp_wav.name)
