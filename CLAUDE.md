# Finance TikTok Video Creator

## Overview
Four tools: (1) Create original TikTok videos from YAML scripts. (2) One-command headline-to-video pipeline. (3) Extract viral clips from YouTube finance videos with AI analysis. (4) Batch search Rumble for trending topics and auto-generate clips.

## Tech Stack
- **Python 3.8** — pipeline orchestration and CLI
- **Remotion (Node.js/React)** — animated text overlays with transparency (PNG sequence → MOV)
- **FFmpeg** — video compositing, audio mixing, clip rendering (ultrafast preset)
- **Edge TTS** — primary TTS (free, unlimited, Microsoft neural voices, default: en-GB-RyanNeural)
- **ElevenLabs / Fish.audio** — premium TTS options (when API keys are active)
- **Pexels API** — stock footage and video clips
- **SerpAPI** — Google Image search for news images + Rumble video search
- **Oracle GenAI** — AI analysis via Gemini 2.5 Flash (full transcript) + Grok 3 Mini (fallback), Instance Principal auth
- **OCI Speech AI** — primary cloud transcription (Whisper Medium), accurate word-level timestamps
- **Vosk** — local fallback: small model (fast transcription), large model (per-word timing)
- **yt-dlp + Deno** — YouTube/Rumble download (Deno solves JS challenges, --impersonate chrome for Rumble)
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
Required: `pexels` (stock footage), `serpapi_key` (news images + Rumble search)
Optional: `elevenlabs`, `fish_audio` (premium TTS), `anthropic` (clip analysis)
Edge TTS needs no key. OCI GenAI uses Instance Principal auth — no key needed on this server.

## Five CLIs

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

### 3. clip_video.py — YouTube/Rumble to TikTok Clips
```bash
# If yt-dlp works directly:
python3 clip_video.py "https://youtube.com/watch?v=VIDEO_ID" --ai oci --max-clips 5
# If YouTube blocks (common on cloud IPs), upload from laptop first:
./upload_video.sh "https://youtube.com/watch?v=VIDEO_ID"
python3 clip_video.py VIDEO_ID --ai oci --skip-download --max-clips 5
# Quality presets:
python3 clip_video.py VIDEO_ID --ai oci --skip-download --quality draft   # fast preview
python3 clip_video.py VIDEO_ID --ai oci --skip-download --quality preview # high quality preview
python3 clip_video.py VIDEO_ID --ai oci --skip-download --quality final   # ready to post
# Options: --no-captions --no-title --skip-face --quality draft|preview|final
```

### 4. rumble_search.py — Rumble Topic Search (single topic)
```bash
python3 rumble_search.py "stock market crash" --max-videos 2 --max-clips 5 --quality final
```
Note: Rumble content quality varies — best used as a supplement to curated YouTube uploads.

### 5. batch_search.py — Parallel Multi-Topic Search
```bash
python3 batch_search.py "tariffs" "mortgage rates" "AI jobs" \
  --clips-per-video 2 --videos-per-topic 1 --quality draft --cleanup
```
Parallel downloads/transcription, auto-cleanup after clip extraction.

## Project Structure
```
quick_video.py           # CLI: headline → video (one command)
create_video.py          # CLI: YAML script → video
clip_video.py            # CLI: YouTube/Rumble → clips
rumble_search.py         # CLI: Rumble topic search → clips
batch_search.py          # CLI: parallel multi-topic batch search
upload_video.sh          # Local: download YT + upload to OCI
platform_utils.py        # Platform detection + FFmpeg encoding args
config.yaml              # API keys (not committed)
pipeline/                # Video creator modules
clipper/                 # Clip generator modules
  analyze.py             #   AI transcript analysis + two-pass title rewriting
  captions.py            #   ASS subtitle generation (karaoke + word-level timing)
  render.py              #   FFmpeg clip rendering + auto-trim silence
  transcribe_clip.py     #   Vosk dual-model transcription
  transcript.py          #   YouTube transcript fetching
  oci_speech.py          #   OCI Speech AI transcription (cloud Whisper)
  detect_captions.py     #   Burned-in caption detection (disabled)
  facedetect.py          #   Face detection for smart cropping
  download.py            #   OCI + yt-dlp download
remotion/src/            # Remotion overlay components
scripts/                 # YAML video scripts
data/videos/             # Downloaded videos (gitignored)
data/models/             # Vosk speech models (gitignored)
```

## Clip Generation Features
- **Karaoke captions**: white text with green highlight, word-by-word timing via OCI Speech AI (falls back to Vosk), border pulse animation, 2 words per group with gap-based splitting
- **Hook quote**: scroll-stopping text shown in first 2 seconds at top of screen (AI generates `hook_quote` field)
- **OCI Speech AI**: primary transcription for per-clip captions — cloud Whisper Medium, accurate word timestamps, ~50s per clip
- **Two-pass AI titles**: first pass finds clips, second pass rewrites titles using actual clip transcript
- **AI-generated TikTok descriptions**: hook line + 5 hashtags, generated during analysis
- **Auto-trim silence**: detects and removes leading/trailing dead air
- **Clip overlap detection**: deduplicates overlapping time ranges
- **Flexible duration**: AI picks 30-45s per clip — short and punchy for TikTok watch-through
- **Burned-in caption detection**: auto-detection disabled (too many false positives) — use `--no-captions` flag manually for videos with existing captions
- **Quality presets**: draft (low bitrate, skip face/vosk), preview (full bitrate, skip face/vosk), final (full quality) — use preview for iteration, final for posting
- **Fade transitions**: 0.3s video + audio fade in/out on all clips
- **Full transcript analysis**: Gemini 2.5 Flash handles up to 200K chars, Grok fallback for coverage
- **Transcription chain**: YouTube transcript (via upload_video.sh) → OCI Speech AI (cloud) → Vosk (local fallback)
- **Pipelined prep+render**: one ThreadPoolExecutor runs `_prepare_and_render` per clip (silence detect → transcribe → face → render). Fast clips finish encoding while slow ones still transcribe — no "all prep, then all render" barrier
- **AI host video** (`host_video.py`): generates a TikTok with 2-3 AI-rendered avatar cutaway scenes (EchoMimic V1 on Modal A10G) inside the existing collage style. Requires Modal token (`~/.modal.toml`) and `modal_app.py` deployed (`python3.9 -m modal deploy modal_app.py`). Portrait at `data/avatar/portrait.png` (real photo works best — AI-generated portraits cause worse lip sync). Use `--no-gpu` for still-portrait fallbacks. Pipeline: `python3 host_video.py "headline"`. ~$0.18/cutaway, ~$0.54/video, free $30/mo on Modal.
- **Perf testing**: use `data/videos/JJeQ8531HgE.mp4` (82MB, transcript cached) as the canonical small test video — `python3 clip_video.py JJeQ8531HgE --ai oci --skip-download --max-clips 3 --quality final` runs the full pipeline in ~2 min

## Source Video Selection
- Best clips come from emotional interviews, confrontations, personal stories with stakes
- Caleb Hammer Financial Audit, Dave Ramsey, Diary of a CEO = high clip density
- Educational explainers / voiceover videos = poor clip quality, avoid
- Longer videos (30-60 min) yield more diverse clips than short ones (<15 min)

## Video Format (Best Performing)
- 8-10 scenes, 2-3 seconds each, ~25-30 seconds total
- Mix of `news_video` (Pexels clips) and `news_image` (SerpAPI) per scene
- No character (takes up screen space, looks automated)
- Hook: 0.6s, word-by-word slam animation with flash + shake
- Captions: word-by-word with yellow highlight (Remotion) or white-to-green karaoke (ASS)
- Voice: en-GB-RyanNeural (Edge TTS, British, authoritative)
- TikTok description: max 5 hashtags

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
- macOS: uses `h264_videotoolbox` (hardware-accelerated), up to 6 parallel render threads
- Linux: uses `libx264` (software), dynamic thread count via `get_thread_count()`
- All FFmpeg encode args go through `get_video_encode_args()` / `get_video_encode_args_simple()`

## Environment Gotchas
- Python 3.8 on server — latest yt-dlp/pytubefix won't install via pip. Use standalone `./yt-dlp` binary
- Deno at `~/.deno/bin/deno` — required for yt-dlp JS challenge solving
- YouTube download inconsistent from cloud IPs — use OCI upload workflow as fallback
- Rumble download works with `--impersonate chrome` flag
- OCI Object Storage: bucket `finance-videos`, namespace `idtd7ksjim3e`, region `us-ashburn-1`
- Remotion WebM VP9 has no alpha on this FFmpeg — use PNG sequence → MOV
- `zoompan` filter at 1080x1920 extremely slow — use blurred bg + centered image instead
- Dual Vosk models: small (40MB) for fast full-video transcription, large (1.8GB) for accurate per-clip word timing
- Edge TTS is the reliable free fallback — ElevenLabs/Fish.audio credits expire
- TTS fallback chain: ElevenLabs → Fish.audio → Edge TTS (always works)
- FFmpeg `-ss` MUST come BEFORE `-i` for ASS subtitle timing
- scene_padding (0.3s) must match between composer and remotion_bridge
- Clip rendering uses ThreadPoolExecutor (dynamic thread count via platform_utils) — not ProcessPoolExecutor (pickle error)
- Vosk large model: must remove/rename `rescore/` dir (has G.carpa not G.fst, causes load failure)
- ASS subtitle `\fscx/\fscy` animation causes vertical text shift — use `\bord` pulse instead
- Gemini 2.5 Flash sometimes returns 0 clips on large transcripts — Grok fallback handles this automatically
- OCI disk resize: `oci-growfs` not available, use `sudo growpart /dev/sda 1 && sudo resize2fs /dev/sda1`
- Rumble search pages blocked by Cloudflare — use SerpAPI `site:rumble.com` queries instead
- YouTube blocks transcript API from cloud IPs too — always upload transcript from Mac via upload_video.sh
- Burned-in caption detection (clipper/detect_captions.py) disabled due to false positives — use --no-captions flag
- OCI Speech AI requires audio uploaded to Object Storage first, results written to speech_output/ prefix
- Server: 32 vCPUs, 62GB RAM, 200GB storage (AMD EPYC Flex shape, upgraded 2026-04-14 from 8 vCPU / 32GB)
- Parallel render threads capped at 12 on Linux (`platform_utils.get_thread_count()`) — each libx264 encode is itself multi-threaded, so higher counts oversubscribe cores
- ffmpeg WAV to pipe leaves RIFF/data chunk sizes as 0xFFFFFFFF (ffmpeg can't seek a pipe) — OCI Speech rejects this. Patch both length fields with `struct.pack_into` before upload (clipper/oci_speech.py)
- OCI GenAI + Speech require explicit dynamic-group policies (`use generative-ai-family`, `use ai-service-speech-family`) — object-storage policies don't grant them. 404 NotAuthorizedOrNotFound = IAM, not code
- Per-clip prep is thread-parallel — silence detect (subprocess), face detect (cv2), OCI Speech (network), Vosk (C ext) all release the GIL. Vosk model loading is locked via `threading.Lock` in clipper/transcribe_clip.py to prevent duplicate loads on cold cache
- clipper/oci_speech.py wraps the whole flow in `except Exception: return []` — silent fallback hides real failures during debugging. Temporarily replace with `traceback.print_exc()` or check `list_transcription_jobs` for FAILED state when OCI Speech mysteriously returns 0 words
- Modal SDK requires Python 3.9+ but the project uses Python 3.8 — `avatar/render.py` shells out to `python3.9` for `modal.Function.from_name().remote()` calls. If Modal calls fail with "client version too old", check which Python is being used.
- Edge TTS `--write-media foo.wav` outputs MP3 with a .wav extension, not real WAV. Lip-sync models (EchoMimic, Hallo2) need real PCM WAV — convert with `ffmpeg -i input.wav -ar 16000 -ac 1 -c:a pcm_s16le output.wav` before passing to avatar render
- LivePortrait (KwaiVGI/LivePortrait) is VIDEO-driven (expression transfer between two videos), NOT audio-driven. Do not use it for `(portrait, audio) → talking head`. Use EchoMimic V1 or Hallo2 instead.
- AI-generated portraits (SDXL, Flux) have facial geometry quirks that degrade lip-sync model output (EchoMimic, Hallo2, MuseTalk, LatentSync). Real photos of real faces produce noticeably better mouth rendering. Always test with a real photo before blaming the model.
- Stop Ollama (`sudo systemctl stop ollama`) when not in use to free RAM
- Multiple Claude sessions with Telegram plugin cause missed messages — kill stale ones

## Telegram
- When receiving a Telegram message, always acknowledge receipt with a quick reply before starting any work
- When sending rendered clips via Telegram, send each clip's TikTok description (hook line + max 5 hashtags) as a separate message so it's easy to copy-paste
- Run clip generation (download, transcribe, render) in the background so the user can still interact during processing
- When sending preview-quality clips, remind the user to pick favorites for final-quality re-rendering

## OCI Video Workflow
```bash
# Download video from OCI and generate clips (most common workflow):
# 1. User runs on Mac: ./upload_video.sh "https://youtube.com/watch?v=VIDEO_ID"
#    This uploads both video + YouTube transcript to OCI
# 2. Download with Python OCI SDK (Instance Principal auth):
python3 -c "
import oci
signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
client = oci.object_storage.ObjectStorageClient({}, signer=signer)
obj = client.get_object('idtd7ksjim3e', 'finance-videos', 'VIDEO_ID.mp4')
with open('data/videos/VIDEO_ID.mp4', 'wb') as f:
    for chunk in obj.data.raw.stream(8192, decode_content=False):
        f.write(chunk)
"
# 3. Generate clips:
python3 clip_video.py VIDEO_ID --ai oci --skip-download --max-clips 5 --quality preview
```

## Output
- Format: H.264 + AAC, 1080x1920, 30fps
- Videos: `output/` directory
- Clips: `output/clips/` directory
- Descriptions: `output/clips/{video_id}_descriptions.json`
