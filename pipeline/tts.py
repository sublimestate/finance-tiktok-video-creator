"""TTS generation for video narration with ElevenLabs + Fish.audio fallback."""

import json
import logging
import os
import subprocess
import requests
from pathlib import Path
from typing import Optional

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
) -> float:
    """Generate TTS audio via ElevenLabs and return duration in seconds."""
    # Resolve voice ID
    if voice_id_cache and voice_name in voice_id_cache:
        voice_id = voice_id_cache[voice_name]
    else:
        voice_id = get_voice_id(api_key, voice_name)
        if voice_id_cache is not None:
            voice_id_cache[voice_name] = voice_id

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

    return get_audio_duration(output_path)


# ---------------------------------------------------------------------------
# Fish.audio
# ---------------------------------------------------------------------------

def _generate_fish_audio(
    api_key: str,
    text: str,
    output_path: str,
    reference_id: Optional[str] = None,
    format: str = "mp3",
) -> float:
    """Generate TTS audio via Fish.audio and return duration in seconds.

    Args:
        api_key: Fish.audio API key (Bearer token).
        text: Text to synthesize.
        output_path: Where to write the audio file.
        reference_id: Optional Fish.audio voice/reference ID for voice selection.
        format: Audio format — "mp3", "wav", or "pcm".
    """
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

    return get_audio_duration(output_path)


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
) -> float:
    """Generate TTS audio and return its duration in seconds.

    Tries ElevenLabs first.  If that fails for any reason (quota exceeded,
    rate limit, network error, etc.) and a Fish.audio API key is configured,
    automatically retries with Fish.audio as a fallback.

    Args:
        api_key: ElevenLabs API key.
        text: The text to synthesise.
        output_path: Destination file path for the audio.
        voice_name: ElevenLabs voice name (prefix-matched).
        model: ElevenLabs model ID.
        stability: ElevenLabs voice stability setting.
        similarity_boost: ElevenLabs similarity boost setting.
        voice_id_cache: Optional dict to cache voice name -> ID lookups.
        fish_audio_api_key: Fish.audio API key. If None, fallback is disabled.
        fish_audio_reference_id: Optional Fish.audio voice/reference ID.

    Returns:
        Audio duration in seconds.
    """
    # --- Attempt 1: ElevenLabs ---
    try:
        duration = _generate_elevenlabs(
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
        return duration
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
        duration = _generate_fish_audio(
            api_key=fish_audio_api_key,
            text=text,
            output_path=output_path,
            reference_id=fish_audio_reference_id,
        )
        logger.info("TTS generated via Fish.audio (fallback) (%s)", output_path)
        return duration
    except Exception as fallback_exc:
        logger.error("Fish.audio fallback also failed: %s", fallback_exc)
        raise
