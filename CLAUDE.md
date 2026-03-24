# Finance TikTok Video Creator

## Overview
Automated pipeline for creating educational TikTok videos about finance. No human presenters — uses stock footage, animated text overlays, and TTS narration.

## Tech Stack
- **Python 3** — pipeline orchestration and CLI
- **Remotion (Node.js/React)** — animated text overlays with transparency (PNG sequence → MOV)
- **FFmpeg** — video compositing, Ken Burns effects, audio mixing, final encoding
- **ElevenLabs** — TTS narration (free tier: 10K chars/month)
- **Fish.audio** — TTS fallback if ElevenLabs fails (quota, rate limit, network error)
- **Pexels API** — stock footage and images

## Project Structure
```
create_video.py          # CLI entry point
config.yaml              # API keys and settings (not committed)
pipeline/
  parser.py              # YAML script → Scene dataclasses
  tts.py                 # TTS generation (ElevenLabs + Fish.audio fallback)
  assets.py              # Pexels/Pixabay stock asset fetching
  remotion_bridge.py     # Python → Remotion CLI (PNG sequence with alpha)
  composer.py            # FFmpeg final compositing
remotion/src/
  index.tsx              # Remotion root composition
  Video.tsx              # Main overlay component
  components/
    AnimatedText.tsx      # Title, subtitle, lower_third, typewriter styles
    IconOverlay.tsx       # Emoji icon animations
    SceneTransition.tsx   # Fade in/out transitions
scripts/                 # YAML video scripts
```

## Usage
```bash
python3 create_video.py scripts/example.yaml
python3 create_video.py scripts/example.yaml --skip-assets --skip-tts  # reuse cached
python3 create_video.py scripts/example.yaml --skip-remotion           # reuse overlay
```

## Pipeline Stages
1. **Parse** — YAML script → Scene list
2. **Assets** — Fetch stock footage/images from Pexels
3. **TTS** — Generate narration via ElevenLabs (falls back to Fish.audio on failure)
4. **Remotion** — Render text/icon overlays as PNG sequence → MOV with alpha
5. **Compose** — FFmpeg layers background + overlay + audio → 1080x1920 MP4

## Key Implementation Details
- Each video gets its own `tmp/<script-name>/` directory to avoid cross-contamination
- Remotion renders PNG sequence (not WebM) to preserve alpha transparency
- Frames are renamed to zero-padded format before FFmpeg conversion
- Voice lookup uses `startswith` matching (e.g., "adam" matches "Adam - Dominant, Firm")
- TTS has automatic fallback: ElevenLabs is tried first; if it fails for any reason (quota exceeded, rate limit, network error), Fish.audio is used as a fallback when a `fish_audio` API key is configured under `api_keys`. Logs indicate which provider was used.
- `--skip-*` flags check for cached files in the per-video tmp directory

## Script Format
YAML with scenes containing: `narration`, `visuals` (type, query, fallback_color), `text_overlay` (content, style, position), and optional `icon`.

## Output
- Format: H.264 + AAC, 1080x1920, 30fps
- Location: `output/` directory
- Filename: slugified title
