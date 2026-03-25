"""Transcribe a specific clip segment for accurate caption timing."""

import json
import os
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import List, Dict

from vosk import Model, KaldiRecognizer

# Cache the vosk model
_MODEL = None
# Prefer large model, fall back to small
_LARGE_MODEL = str(Path(__file__).parent.parent / "data" / "models" / "vosk-model-en-us-0.22")
_SMALL_MODEL = str(Path(__file__).parent.parent / "data" / "models" / "vosk-model-small-en-us-0.15")
_MODEL_PATH = _LARGE_MODEL if os.path.exists(_LARGE_MODEL) else _SMALL_MODEL


def _get_model():
    global _MODEL
    if _MODEL is None and os.path.exists(_MODEL_PATH):
        _MODEL = Model(_MODEL_PATH)
    return _MODEL


def transcribe_clip(video_path: str, start_time: float, end_time: float) -> List[Dict]:
    """Transcribe a specific clip segment with accurate word timing.

    Returns list of {"start": float, "end": float, "text": str} with
    timestamps relative to clip start (0-based).
    """
    model = _get_model()
    if model is None:
        return []

    # Extract audio for this clip segment
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
