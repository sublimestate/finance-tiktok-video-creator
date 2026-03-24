"""TTS generation for video narration with ElevenLabs + Fish.audio fallback."""

import base64
import json
import logging
import os
import subprocess
import requests
from pathlib import Path
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ElevenLabs
# ---------------------------------------------------------------------------

def get_voice_id(api_key: str, voice_name: str) -> str:
    """Look up an ElevenLabs voice ID by name."""
    resp = requests.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": api_key},
    )
    resp.raise_for_status()
    for voice in resp.json().get("voices", []):
        if voice["name"].lower().startswith(voice_name.lower()):
            return voice["voice_id"]
    raise ValueError(f"Voice '{voice_name}' not found. Available: "
                     + ", ".join(v["name"] for v in resp.json()["voices"]))


def _generate_elevenlabs(
    api_key: str,
    text: str,
    output_path: str,
    voice_name: str = "adam",
    model: str = "eleven_multilingual_v2",
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    voice_id_cache: Optional[dict] = None,
) -> Tuple[float, List[dict]]:
    """Generate TTS audio via ElevenLabs with word timestamps.

    Returns:
        Tuple of (duration_seconds, word_timings) where word_timings is a list
        of {"word": str, "start": float, "end": float}.
    """
    # Resolve voice ID
    if voice_id_cache and voice_name in voice_id_cache:
        voice_id = voice_id_cache[voice_name]
    else:
        voice_id = get_voice_id(api_key, voice_name)
        if voice_id_cache is not None:
            voice_id_cache[voice_name] = voice_id

    # Try with-timestamps endpoint first
    word_timings = []
    try:
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "text": text,
                "model_id": model,
                "voice_settings": {
                    "stability": stability,
                    "similarity_boost": similarity_boost,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract audio
        audio_bytes = base64.b64decode(data.get("audio_base64", ""))
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        # Extract word timings from alignment
        alignment = data.get("alignment", {})
        chars = alignment.get("characters", [])
        char_starts = alignment.get("character_start_times_seconds", [])
        char_ends = alignment.get("character_end_times_seconds", [])

        if chars and char_starts and char_ends:
            # Build words from characters
            current_word = ""
            word_start = 0.0
            word_end = 0.0
            for i, char in enumerate(chars):
                if char == " " or i == len(chars) - 1:
                    if i == len(chars) - 1 and char != " ":
                        current_word += char
                        word_end = char_ends[i] if i < len(char_ends) else word_end
                    if current_word.strip():
                        word_timings.append({
                            "word": current_word.strip(),
                            "start": word_start,
                            "end": word_end,
                        })
                    current_word = ""
                    if i + 1 < len(char_starts):
                        word_start = char_starts[i + 1]
                else:
                    if not current_word:
                        word_start = char_starts[i] if i < len(char_starts) else word_start
                    current_word += char
                    word_end = char_ends[i] if i < len(char_ends) else word_end

        duration = get_audio_duration(output_path)
        return duration, word_timings

    except Exception as e:
        logger.warning("ElevenLabs with-timestamps failed, falling back to standard: %s", e)

    # Fallback to standard endpoint (no timestamps)
    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": model,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
            },
        },
    )
    resp.raise_for_status()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(resp.content)

    duration = get_audio_duration(output_path)
    # Estimate word timings
    word_timings = _estimate_word_timings(text, duration)
    return duration, word_timings


def _estimate_word_timings(text: str, duration: float) -> List[dict]:
    """Estimate word timings by distributing evenly across duration."""
    words = text.split()
    if not words:
        return []
    # Weight by character count for more natural distribution
    total_chars = sum(len(w) for w in words)
    if total_chars == 0:
        return []
    timings = []
    current_time = 0.05  # small initial offset
    usable_duration = duration - 0.1  # leave small buffer at end
    for word in words:
        word_duration = (len(word) / total_chars) * usable_duration
        timings.append({
            "word": word,
            "start": round(current_time, 3),
            "end": round(current_time + word_duration, 3),
        })
        current_time += word_duration
    return timings


# ---------------------------------------------------------------------------
# Fish.audio
# ---------------------------------------------------------------------------

def _generate_fish_audio(
    api_key: str,
    text: str,
    output_path: str,
    reference_id: Optional[str] = None,
    format: str = "mp3",
) -> Tuple[float, List[dict]]:
    """Generate TTS audio via Fish.audio and return (duration, word_timings)."""
    payload = {
        "text": text,
        "format": format,
    }
    if reference_id:
        payload["reference_id"] = reference_id

    resp = requests.post(
        "https://api.fish.audio/v1/tts",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    resp.raise_for_status()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(resp.content)

    duration = get_audio_duration(output_path)
    word_timings = _estimate_word_timings(text, duration)
    return duration, word_timings


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def get_audio_duration(path: str) -> float:
    """Get duration of an audio file in seconds using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", path],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


# ---------------------------------------------------------------------------
# Public API — tries ElevenLabs first, falls back to Fish.audio
# ---------------------------------------------------------------------------

def generate_tts(
    api_key: str,
    text: str,
    output_path: str,
    voice_name: str = "adam",
    model: str = "eleven_multilingual_v2",
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    voice_id_cache: Optional[dict] = None,
    fish_audio_api_key: Optional[str] = None,
    fish_audio_reference_id: Optional[str] = None,
) -> Tuple[float, List[dict]]:
    """Generate TTS audio and return (duration, word_timings).

    Tries ElevenLabs first. If that fails, falls back to Fish.audio.

    Returns:
        Tuple of (duration_seconds, word_timings).
    """
    # --- Attempt 1: ElevenLabs ---
    try:
        duration, word_timings = _generate_elevenlabs(
            api_key=api_key,
            text=text,
            output_path=output_path,
            voice_name=voice_name,
            model=model,
            stability=stability,
            similarity_boost=similarity_boost,
            voice_id_cache=voice_id_cache,
        )
        logger.info("TTS generated via ElevenLabs (%s)", output_path)
        return duration, word_timings
    except Exception as exc:
        logger.warning("ElevenLabs TTS failed: %s", exc)

        if not fish_audio_api_key:
            logger.error(
                "No Fish.audio API key configured — cannot fall back. "
                "Re-raising original ElevenLabs error."
            )
            raise

    # --- Attempt 2: Fish.audio fallback ---
    logger.info("Falling back to Fish.audio for TTS...")
    try:
        duration, word_timings = _generate_fish_audio(
            api_key=fish_audio_api_key,
            text=text,
            output_path=output_path,
            reference_id=fish_audio_reference_id,
        )
        logger.info("TTS generated via Fish.audio (fallback) (%s)", output_path)
        return duration, word_timings
    except Exception as fallback_exc:
        logger.error("Fish.audio fallback also failed: %s", fallback_exc)
        raise
