# Finance TikTok Video Creator

## Overview
Two tools: (1) Create original TikTok videos from YAML scripts with TTS, overlays, and stock footage. (2) Extract viral clips from YouTube finance videos with AI analysis and karaoke captions.

## Tech Stack
- **Python 3** — pipeline orchestration and CLI
- **Remotion (Node.js/React)** — animated text overlays with transparency (PNG sequence → MOV)
- **FFmpeg** — video compositing, Ken Burns effects, audio mixing, final encoding
- **ElevenLabs** — TTS narration (free tier: 10K chars/month)
- **Fish.audio** — TTS fallback if ElevenLabs fails (quota, rate limit, network error)
- **Pexels API** — stock footage and images
- **SerpAPI** — Google Image search for news/event images (filters stock photo sites)
- **Oracle GenAI** — AI transcript analysis via Grok 3 Mini (Instance Principal auth)
- **Vosk** — offline speech recognition for caption generation
- **yt-dlp + Deno** — YouTube video download (Deno required for JS challenge solving)
- **OCI Object Storage** — HD video upload/download (bucket: finance-videos)
- **Lottie** — animated character via @remotion/lottie

## Project Structure
```
create_video.py          # CLI: create videos from YAML scripts
clip_video.py            # CLI: extract clips from YouTube videos
upload_video.sh          # Local script: download YT + upload to OCI
config.yaml              # API keys and settings (not committed)
pipeline/
  parser.py              # YAML script → Scene dataclasses
  tts.py                 # TTS generation (ElevenLabs + Fish.audio fallback)
  assets.py              # Pexels/Pixabay/SerpAPI/DuckDuckGo asset fetching
  remotion_bridge.py     # Python → Remotion CLI (PNG sequence with alpha)
  composer.py            # FFmpeg final compositing
clipper/
  download.py            # YouTube download via yt-dlp + OCI Object Storage
  transcript.py          # Transcript via yt-dlp subtitles + vosk fallback
  analyze.py             # AI clip selection (OCI GenAI, Anthropic, Ollama)
  facedetect.py          # OpenCV face detection for smart cropping
  captions.py            # ASS karaoke subtitle generation
  render.py              # FFmpeg vertical clip rendering
  transcribe_clip.py     # Per-clip speech recognition via vosk
remotion/src/
  index.tsx              # Remotion root composition
  Video.tsx              # Main overlay component
  components/
    AnimatedText.tsx      # Title, subtitle, lower_third, typewriter styles
    HookText.tsx          # Hook animations: bold, glitch, zoom
    LottieCharacter.tsx   # Animated Lottie character (commentary mode)
    Captions.tsx          # Word-by-word animated captions
    IconOverlay.tsx       # Emoji icon animations
    SceneTransition.tsx   # Fade in/out transitions
scripts/                 # YAML video scripts
```

## Video Creator Usage
```bash
python3 create_video.py scripts/example.yaml
python3 create_video.py scripts/example.yaml --skip-assets --skip-tts  # reuse cached
python3 create_video.py scripts/example.yaml --skip-remotion           # reuse overlay
```

## Clip Generator Usage
```bash
# On your laptop: download HD + upload to OCI
./upload_video.sh "https://youtube.com/watch?v=VIDEO_ID"
# On server: generate clips
python3 clip_video.py VIDEO_ID --ai oci --max-clips 5
python3 clip_video.py VIDEO_ID --ai oci --no-captions --no-title --skip-face
```

## Pipeline Stages (Video Creator)
1. **Parse** — YAML script → Scene list
2. **Assets** — Fetch stock footage/images from Pexels/SerpAPI
3. **TTS** — Generate narration via ElevenLabs (falls back to Fish.audio on failure)
4. **Remotion** — Render text/icon overlays as PNG sequence → MOV with alpha
5. **Compose** — FFmpeg layers background + overlay + audio → 1080x1920 MP4

## Pipeline Stages (Clip Generator)
1. **Download** — OCI Object Storage → yt-dlp fallback
2. **Transcript** — yt-dlp subtitles → vosk speech recognition fallback
3. **AI Analysis** — OCI GenAI (Grok 3 Mini) identifies 3-5 viral moments
4. **Render** — FFmpeg: blurred background + centered frame + ASS karaoke captions

## Script Format
YAML with: `hook` (text, duration, style), `character` (bool), scenes with `narration`, `visuals` (type: stock_video/stock_image/news_image/news_video), `text_overlay`, `icon`.

## Environment Gotchas
- Python 3.8 on this server — latest yt-dlp needs standalone binary (`./yt-dlp`) not pip
- Deno required at `~/.deno/bin/deno` for yt-dlp YouTube JS challenge solving
- YouTube blocks downloads/transcripts from cloud IPs — use cookies or OCI Object Storage upload workflow
- Remotion WebM VP9 does NOT support alpha on this FFmpeg version — use PNG sequence → MOV instead
- `zoompan` filter at 1080x1920 is extremely slow — pre-resize images first, with timeout fallback
- Large vosk model (1.8GB) causes OOM with HD videos — use small model (40MB)
- Stop Ollama (`sudo systemctl stop ollama`) when not in use to free ~5GB RAM
- OCI Instance Principal auth works — dynamic group needs policies for generative-ai-family and object-storage
- SerpAPI image search: filter out stock photo domains (shutterstock, getty, etc.) to avoid watermarks
- Per-video tmp dirs (`tmp/<script-name>/`) prevent cross-contamination between renders
- FFmpeg `-ss` MUST come BEFORE `-i` for ASS subtitle timing to work correctly
- scene_padding (0.3s) must be added to Remotion overlay duration to prevent caption drift

## Output
- Format: H.264 + AAC, 1080x1920, 30fps
- Location: `output/` directory (videos), `output/clips/` (clips)
