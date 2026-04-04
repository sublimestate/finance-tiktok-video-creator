# Finance TikTok Video Creator

## Overview
Three tools: (1) Create original TikTok videos from YAML scripts. (2) One-command headline-to-video pipeline. (3) Extract viral clips from YouTube finance videos with AI analysis.

## Tech Stack
- **Python 3.8** — pipeline orchestration and CLI
- **Remotion (Node.js/React)** — animated text overlays with transparency (PNG sequence → MOV)
- **FFmpeg** — video compositing, audio mixing, clip rendering (ultrafast preset)
- **Edge TTS** — primary TTS (free, unlimited, Microsoft neural voices, default: en-GB-RyanNeural)
- **ElevenLabs / Fish.audio** — premium TTS options (when API keys are active)
- **Pexels API** — stock footage and video clips
- **SerpAPI** — Google Image search for news images (filters stock photo watermarks)
- **Oracle GenAI** — AI analysis via Grok 3 Mini / Gemini (Instance Principal auth)
- **Vosk** — offline speech recognition for captions (small model to avoid OOM)
- **yt-dlp + Deno** — YouTube download (Deno solves JS challenges, inconsistent on cloud IPs)
- **OCI Object Storage** — HD video upload/download (bucket: finance-videos, namespace: idtd7ksjim3e)

## Setup (Oracle Server — Linux)
```bash
# System deps (already installed on server)
# ffmpeg, deno (~/.deno/bin), opencv-python-headless, vosk

# Python deps
python3 -m pip install pyyaml requests python-slugify youtube-transcript-api vosk opencv-python-headless oci edge-tts

# Remotion deps
cd remotion && npm install && cd ..

# Config
cp config.yaml.example config.yaml  # then fill in API keys
```

## Setup (macOS — M-series Mac)
```bash
brew install ffmpeg deno node
python3 -m pip install pyyaml requests python-slugify youtube-transcript-api vosk opencv-python-headless oci edge-tts
cd remotion && npm install && cd ..

# Config
cp config.yaml.example config.yaml  # then fill in API keys
```

## Config Keys (config.yaml)
Required: `pexels` (stock footage), `serpapi_key` (news images)
Optional: `elevenlabs`, `fish_audio` (premium TTS), `anthropic` (clip analysis)
Edge TTS needs no key. OCI GenAI uses Instance Principal auth — no key needed on this server.

## Three CLIs

### 1. quick_video.py — Headline to TikTok (fastest)
```bash
python3 quick_video.py "Oil prices crash 5% on Iran peace deal"
```
Auto-researches topic → AI writes script → fetches assets → TTS → renders. ~6 min.

### 2. create_video.py — Script to TikTok
```bash
python3 create_video.py scripts/example.yaml
python3 create_video.py scripts/example.yaml --skip-assets --skip-tts --skip-remotion
```

### 3. clip_video.py — YouTube to TikTok Clips
```bash
# If yt-dlp works directly:
python3 clip_video.py "https://youtube.com/watch?v=VIDEO_ID" --ai oci --max-clips 5
# If YouTube blocks (common on cloud IPs), upload from laptop first:
./upload_video.sh "https://youtube.com/watch?v=VIDEO_ID"
python3 clip_video.py VIDEO_ID --ai oci --skip-download --max-clips 5
# Options: --no-captions --no-title --skip-face
```

## Project Structure
```
quick_video.py           # CLI: headline → video (one command)
create_video.py          # CLI: YAML script → video
clip_video.py            # CLI: YouTube → clips
upload_video.sh          # Local: download YT + upload to OCI
platform_utils.py        # Platform detection + FFmpeg encoding args
config.yaml              # API keys (not committed)
pipeline/                # Video creator modules
clipper/                 # YouTube clip generator modules
remotion/src/            # Remotion overlay components
scripts/                 # YAML video scripts
data/videos/             # Downloaded YouTube videos (gitignored)
data/models/             # Vosk speech models (gitignored)
```

## Video Format (Best Performing)
- 8-10 scenes, 2-3 seconds each, ~25-30 seconds total
- Mix of `news_video` (Pexels clips) and `news_image` (SerpAPI) per scene
- No character (takes up screen space, looks automated)
- Hook: 0.6s, word-by-word slam animation with flash + shake
- Captions: word-by-word with yellow highlight (Remotion) or white-to-green karaoke (ASS)
- Voice: en-GB-RyanNeural (Edge TTS, British, authoritative)
- TikTok description: max 6 hashtags

## Script Format
```yaml
title: "Title"
voice: "adam"
character: false
hook:
  text: "HOOK IN CAPS"
  duration: 0.6
  style: glitch  # bold | glitch | zoom
scenes:
  - narration: "Short punchy sentence."
    duration: 2.5
    visuals:
      type: news_video  # news_video | news_image | stock_video | stock_image | solid_color
      query: "search query for visuals"
    text_overlay:
      content: "Key Point"
      style: title  # title | subtitle | lower_third | typewriter
      position: center  # center | top | bottom
    icon: "fire"  # optional emoji icon
```

## Platform-Aware Encoding
- `platform_utils.py` auto-detects macOS vs Linux and selects the best FFmpeg encoder
- macOS: uses `h264_videotoolbox` (hardware-accelerated), more parallel render threads
- Linux: uses `libx264` (software), 3 parallel render threads
- All FFmpeg encode args go through `get_video_encode_args()` / `get_video_encode_args_simple()`

## Environment Gotchas
- Python 3.8 on server — latest yt-dlp/pytubefix won't install via pip. Use standalone `./yt-dlp` binary
- Deno at `~/.deno/bin/deno` — required for yt-dlp JS challenge solving
- YouTube download inconsistent from cloud IPs — some videos work, others blocked. Use OCI upload workflow as fallback
- OCI Object Storage upload script names files with full URL — server auto-renames to video ID
- Remotion WebM VP9 has no alpha on this FFmpeg — use PNG sequence → MOV
- `zoompan` filter at 1080x1920 extremely slow — use blurred bg + centered image instead
- Small vosk model only (40MB) — large model (1.8GB) causes OOM with HD videos
- Edge TTS is the reliable free fallback — ElevenLabs/Fish.audio credits expire
- TTS fallback chain: ElevenLabs → Fish.audio → Edge TTS (always works)
- FFmpeg `-ss` MUST come BEFORE `-i` for ASS subtitle timing
- scene_padding (0.3s) must match between composer and remotion_bridge
- Clip rendering uses ThreadPoolExecutor (dynamic thread count via platform_utils) — not ProcessPoolExecutor (pickle error)
- OCI free trial limits instance creation — may need PAYG upgrade for more compute
- No GPU shapes available in us-ashburn-1 — would need service limit increase or different region
- Stop Ollama (`sudo systemctl stop ollama`) when not in use to free RAM
- Multiple Claude sessions with Telegram plugin cause missed messages — kill stale ones

## Telegram
- When receiving a Telegram message, always acknowledge receipt with a quick reply before starting any work
- When sending rendered clips via Telegram, always include a TikTok description (hook line + max 6 hashtags) with each clip

## Output
- Format: H.264 + AAC, 1080x1920, 30fps
- Videos: `output/` directory
- Clips: `output/clips/` directory
