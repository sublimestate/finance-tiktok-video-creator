# AI Host Video — Design

**Date:** 2026-04-14
**Status:** Approved for implementation planning
**Goal:** Add a new video format that features a recurring AI-generated host appearing as cutaways throughout the existing collage style, building brand identity and on-screen engagement.

## Why

The existing pipelines (`quick_video.py`, `clip_video.py`) produce TikTok finance videos as a Pexels stock-footage collage with TTS narration and text overlays. There is no recurring face — every video looks anonymous. A recurring AI-generated host solves two related problems:

- **Brand identity.** Viewers recognize a single "channel personality" across videos.
- **Engagement.** A face on screen typically outperforms stock footage alone.

This design avoids SaaS lock-in (HeyGen, Synthesia, D-ID) by generating the character once with an open-source diffusion model and animating it with an open-source talking-head model on a rented GPU. The host is owned outright; cost shifts from SaaS subscription to per-render GPU compute.

## Scope

A new CLI alongside the existing tools. **No changes to `quick_video.py` or `clip_video.py`.** Only `pipeline/composer.py` gets a small extension.

In scope for v1:
- New CLI `host_video.py` (headline → avatar-cutaway video)
- New one-shot `setup_host.py` (generate the recurring character portrait)
- New `avatar/` module (LivePortrait on RunPod via REST)
- Minimum extension to `pipeline/composer.py` to accept a per-scene mp4 override

Out of scope for v1:
- Multiple host characters / character library
- Picture-in-picture composition (avatar + B-roll simultaneously)
- Avatar in `clip_video.py` (audio belongs to the source video; brand consistency wouldn't hold)
- Automated visual quality checks
- Hand gesturing, full-body avatars, multi-shot framing

## Architecture

A new layered surface that mirrors the existing pattern (CLI orchestrator on top of focused modules):

```
host_video.py              # NEW CLI: headline → avatar-cutaway video
setup_host.py              # NEW one-shot: generate the recurring character portrait

avatar/                    # NEW module
  render.py                #   high-level: render_cutaway(portrait, audio) → mp4
  runpod.py                #   RunPod REST client: pod start/stop, job submit, result fetch
  character.py             #   load/save the character portrait + voice config

data/avatar/               # NEW (gitignored)
  portrait.png             #   the recurring host (one-time setup output)
  portrait.png.bak         #   previous portrait, for rollback
  candidates/              #   Flux portrait candidates from setup_host.py
  character.yaml           #   { name, voice, prompt_used, created }
  billing.log              #   per-day RunPod-seconds counter

pipeline/                  # EXISTING — minor extension
  composer.py              #   accept a {scene_index → mp4} override map for cutaway scenes

docs/superpowers/specs/    # this document lives here
```

The avatar renderer (`avatar/`) does not know about scripts, scenes, or the existing pipeline — it only knows `(portrait, audio) → mp4`. `host_video.py` does the orchestration and the existing composer gets a tiny extension to accept "use this mp4 as the visual for scene N" for cutaway scenes.

## Data Flow

```
python3 host_video.py "Oil prices crash 5% on Iran peace deal"

  1. Research topic         (reuse quick_video.py logic — SerpAPI/news fetch)
  2. AI script generation   (NEW prompt: ~8 scenes total, marks 2-3 as host beats)
  3. Edge TTS per scene     (reuse — generate one wav per scene)
  4. Asset fetch            (reuse — Pexels for non-host scenes)
  5. RunPod pod start       (kicked off in parallel with steps 3-4 to hide cold start)
  6. Avatar batch render    (submit all host-beat scenes at once → talking_head_N.mp4)
  7. RunPod pod stop        (always — even on error, via context manager)
  8. Composer assembly      (host scenes use avatar mp4, others use existing collage)
  9. Final render           (reuse remotion + ffmpeg pipeline)

  Output: output/host/<slugified_headline>.mp4
```

Two key efficiency moves:

- **Steps 3–6 overlap.** Pod boot is the long pole (~60–90s). Kick it off in parallel with TTS + asset fetch. By the time the audio is ready, the pod is warm.
- **Single pod session per video, not per cutaway.** All 2–3 cutaways render in one batch on one warm pod. Pod start/stop happens once per video, so cost is ~$0.02/video instead of ~$0.06.

## RunPod GPU Lifecycle

The most failure-prone part of the design — getting GPU lifecycle right is what keeps the cost story honest.

```python
class RunPodSession:
    def __enter__(self):           # spin up A10 pod via REST API, wait for ready
    def render(portrait, audio):   # submit one job to running pod, return mp4 path
    def render_batch(jobs):        # submit N jobs concurrently to one pod
    def __exit__(self, *exc):      # stop pod (always — even on error)
```

Used as:

```python
with RunPodSession(image="liveportrait-runpod:latest") as pod:
    cutaways = pod.render_batch([
        (portrait, scene_2_audio),
        (portrait, scene_5_audio),
        (portrait, scene_7_audio),
    ])
```

### Critical behaviors

- **Context manager guarantees teardown.** Even on Python exception, `__exit__` calls `pod.stop()` — no orphaned $0.34/hr billing. This is the only safety net for cost overruns.
- **Pod boot ~60–90s.** Started early in `host_video.py` (parallel with TTS/asset fetch), so by the time audio is ready the pod is warm.
- **Image is pre-built and pinned.** A Docker image with LivePortrait + weights baked in, pushed to RunPod's container registry. Cold start without baked weights is 5–10 min — unacceptable.
- **Pod-ready signal must be robust.** RunPod's API is eventually-consistent — the pod can report "running" before the inner service is actually accepting requests. The session waits for an HTTP 200 from the inner service's healthcheck, not just the RunPod API status.
- **Hard timeout per render.** 5-minute cap per cutaway. If LivePortrait hangs, the job is killed, that single beat falls back to a still portrait + audio, and the rest of the batch continues. The video still ships.

### Cost guardrails

- Env var `MAX_RUNPOD_SECONDS_PER_RUN` (default 600s = $0.06). Enforced in `RunPodSession.__exit__` — if exceeded, log a clear warning. Prevents a runaway from silently billing hundreds.
- Per-day counter at `data/avatar/billing.log`. Append `(date, seconds, estimated_cost)` after every session. Lets you spot-check actual cost vs estimate.

### Day-one focus

Plan to spend most of the first day's work on two pieces: (1) building the Docker image with weights baked in and pushing it to the registry, and (2) handling the "pod ready" signal robustly. Everything else in `avatar/runpod.py` is straightforward REST plumbing.

## Avatar Renderer Module

`avatar/render.py` exposes one high-level function:

```python
def render_cutaway(
    portrait_path: str,
    audio_path: str,
    output_path: str,
    *,
    timeout_seconds: int = 300,
    fallback_on_failure: bool = True,
) -> str:
    """Render one talking-head cutaway. Returns the output mp4 path.

    On any failure (timeout, RunPod error, garbage output), if
    fallback_on_failure is True, writes a still-portrait video with
    the audio at output_path and returns it. Otherwise raises.
    """
```

Internally it uses a `RunPodSession` from `avatar/runpod.py`. For batch use, `host_video.py` opens a single session and calls `pod.render_batch([...])` directly so all cutaways for one video share one pod.

`avatar/character.py` exposes:

```python
def load_character() -> Character:  # reads data/avatar/portrait.png + character.yaml
def save_character(portrait_bytes: bytes, prompt: str, voice: str) -> None
```

## AI Script Prompt for Host Beats

The script-generation prompt outputs YAML in the existing `create_video.py` format with one new optional field per scene: `speaker: host`. Scenes without it default to collage style.

```yaml
title: "Oil Crashes 5%"
hook: { text: "OIL JUST CRASHED", duration: 0.6, style: glitch }
scenes:
  - narration: "Crude oil prices fell 5% in overnight trading."
    duration: 3.0
    visuals: { type: news_video, query: "oil pump jack" }
  - narration: "Iran and the US announced a peace framework."
    duration: 3.0
    visuals: { type: news_image, query: "Iran US flags handshake" }
  - narration: "And here's why every American driver is about to feel it."
    duration: 4.0
    speaker: host           # ← AI marks this as a cutaway
  - narration: "Gas stations across the country..."
    duration: 3.0
    visuals: { type: news_video, query: "gas station prices" }
```

### Prompt rules the AI must follow

- Total scenes: 8–10 (matches existing format)
- Mark exactly **2 or 3** scenes as `speaker: host`
- Host beats are **3–5 seconds** each, written in **first person, conversational** ("Here's the thing", "Watch this", "Trust me on this")
- Pick beats that are **interpretive or opinionated** — the punchline, the "why this matters", the call to action — not factual recital. Collage is for facts; host is for tone.
- The **first and last** scenes should NOT both be host beats (avoid the "host opens, host closes" feel — too formulaic)
- Host beat narration must use **concrete language**, not "in the previous scene" / "as I said". Each scene must stand on its own in case a host beat gets degraded to a still-portrait fallback.

### Why these constraints

They force the AI to use the host as a *voice of the channel* (opinion, tone, perspective) and the collage as the *evidence* (visuals, headlines, numbers). That separation matches how human TikTok finance creators actually use cutaways and is what makes brand identity stick.

The AI backend stays the same as `quick_video.py` — Gemini 2.5 Flash on OCI GenAI, with the existing Grok fallback pattern.

## Character Setup (One-Time)

The recurring host is generated once, saved to `data/avatar/portrait.png`, and reused forever. A separate one-shot script handles this so build/burn-in only happens when you actually want to refresh the character.

```
setup_host.py [--regenerate] [--prompt "..."]
```

### Default flow (first run)

1. Generate **4 portrait candidates** via Flux on Replicate (~$0.05 total). One-time, doesn't need our own GPU pipeline.
2. Save all 4 to `data/avatar/candidates/` and tile them into a single 2x2 preview image at `data/avatar/candidates/preview.png`.
3. Open the preview in the system viewer and ask which one to keep (1, 2, 3, or 4).
4. Save the chosen one to `data/avatar/portrait.png` and write `data/avatar/character.yaml`:
   ```yaml
   name: "Ryan"            # editable
   voice: en-GB-RyanNeural # matches existing pipeline default
   prompt_used: "..."       # so we can regenerate if a frame gets corrupted
   created: 2026-04-14
   ```

### Why Replicate for setup, RunPod for production

Flux portrait generation is a one-off setup task. Paying Replicate's per-call markup once is not worth provisioning a second GPU pipeline. The actual production renderer still runs on RunPod LivePortrait as designed.

### Portrait constraints baked into the prompt

- Head and shoulders, looking slightly off-center toward camera
- Neutral background (LivePortrait performs better with clean backgrounds)
- Neutral expression (so the model has the most room to animate)
- Lighting from the front-left (matches what looks natural in a 9:16 frame)
- Apparent age 28–40, gender to match `voice` (default British male for "Ryan")

### Regeneration

`--regenerate` re-runs candidate generation. `--prompt "..."` overrides the default prompt entirely. The `character.yaml` is updated, and the **previous** portrait is preserved at `data/avatar/portrait.png.bak` so you can roll back if a regeneration looks worse.

## Composer Extension

`pipeline/composer.py` gets one small change: accept a `cutaway_overrides: dict[int, str]` parameter mapping scene index to a pre-rendered mp4 path. For scenes in the override map, the composer uses the provided mp4 as the visual instead of running the normal Pexels/SerpAPI fetch + Remotion overlay path. Captions and audio still come from the standard pipeline so the cutaway integrates cleanly.

This is intentionally a tiny extension — the alternative (a parallel composer for host videos) would duplicate ~80% of the existing logic.

## Error Handling

The principle is the same as the existing pipeline: **prefer a degraded video that ships over a perfect video that fails**. Every failure path leaves a working .mp4.

| Failure | What happens |
|---|---|
| RunPod API down / no GPUs available | All host beats fall back to still-portrait + audio. Video still ships. Logged as warning. |
| Pod boots but render hangs | 5-min per-render timeout kills the job. That single beat falls back to still portrait. Other beats continue. |
| Pod boots fine but outputs garbage frames | Hard to detect automatically. Out of scope for v1 — relies on manual review of first batches. |
| Replicate Flux call fails during `setup_host.py` | One-shot script errors out with a clear message. No production impact. |
| `data/avatar/portrait.png` missing when `host_video.py` runs | Hard error: "Run `python3 setup_host.py` first." |
| Edge TTS fails for a host-beat scene | Existing fallback chain (ElevenLabs → Fish.audio → Edge TTS). If all fail, that beat becomes a silent collage scene and the video continues. |
| AI script generation returns 0 host beats | Falls back to standard collage video — equivalent to running `quick_video.py`. |
| Composer can't read the avatar mp4 | Single beat falls back to still portrait. |

## Testing

Three layers, in order of frequency:

1. **`avatar/render.py` in isolation.** Test fixture: a known portrait + 3-second audio of a sentence → render → assert the output is a valid mp4 of the right duration. Run before any host_video.py change. Fast feedback loop.
2. **RunPod client mocked.** Test the lifecycle (start, submit, wait, fetch, stop) against a stub HTTP server so unit tests don't burn $0.34 each. Asserts: pod always stops, batch jobs all complete, timeout actually fires.
3. **End-to-end with a recorded fixture headline.** A canonical "perf-test" headline that runs the full pipeline once. Wall-time budget ~5 min. Catches regressions in script generation, composer integration, or RunPod behavior. Run manually before commits to `host_video.py`.

There is no automated visual quality check — that requires human eyes. A run script that opens the latest output mp4 in a viewer is the manual gate.

## Cost Model

Per-video, with 2–3 cutaways totalling ~12s of avatar:

- LivePortrait on RunPod A10: ~20–40s render per cutaway → 1–2 min total GPU time per video
- A10 hourly rate: ~$0.34/hr → **~$0.02–$0.05 per video**
- Replicate Flux for `setup_host.py`: ~$0.05 once, then never again (unless regenerating)

Daily budget guardrail: `MAX_RUNPOD_SECONDS_PER_RUN=600` (= $0.06/run), enforced in `RunPodSession.__exit__`. A runaway is logged loudly so you notice before it bills hundreds.

## Open Questions

None blocking implementation. Items to monitor after first batch:

- Whether 2–3 host beats per video is the right rhythm or if 1–4 with a wider variance produces better videos
- Whether LivePortrait quality holds across topics or shows tells on certain expression patterns (anger, surprise, laughter)
- Whether the static portrait should be refreshed periodically (e.g., different lighting per quarter) for visual variety without changing identity

These are all post-launch tuning questions, not v1 blockers.

## Summary

A new `host_video.py` CLI takes a headline, generates an 8–10 scene script with 2–3 marked as host cutaways, renders the host scenes via LivePortrait on a per-video RunPod A10 session (single pod start/stop, batched), and composites everything through a minor extension to the existing composer. The recurring character is generated once via `setup_host.py` using Flux on Replicate. Cost ~$0.02–$0.05 per video, no SaaS lock-in, fail-soft fallbacks at every step.
