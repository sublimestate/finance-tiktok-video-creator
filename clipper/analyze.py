"""AI-powered transcript analysis to identify viral clip segments."""

import json
import requests
from typing import List, Dict, Optional

try:
    import oci
    HAS_OCI = True
except ImportError:
    HAS_OCI = False


SYSTEM_PROMPT = """You are an expert short-form video editor specializing in finance content for TikTok and YouTube Shorts.

Your job is to analyze video transcripts and identify the most engaging 30-60 second segments that would perform well as standalone short-form clips.

Selection criteria (prioritize segments with these qualities):
- **Strong opening hook**: A bold claim, surprising statistic, or provocative question in the first 3 seconds
- **Emotional peaks**: Moments of excitement, urgency, or conviction from the speaker
- **Contrarian takes**: Opinions that go against conventional wisdom
- **Actionable advice**: Concrete tips viewers can apply immediately
- **Surprising statistics or facts**: Numbers that shock or educate
- **Quotable statements**: Memorable one-liners or analogies
- **Story moments**: Mini-narratives with a clear beginning, middle, and punchline

Rules:
- Each clip MUST be between 30 and 60 seconds
- Clips should start at a natural beginning of a thought (not mid-sentence)
- Clips should end at a natural conclusion or punchline
- Avoid segments that require too much prior context to understand
- Identify 3-5 clips per video
- Score each clip 1-100 based on estimated viral potential"""


def build_user_prompt(video_title: str, transcript: str) -> str:
    return f"""Analyze this finance video transcript and identify the best clips for TikTok/YouTube Shorts.

Video title: "{video_title}"

Transcript:
{transcript}

You MUST respond with valid JSON matching this exact format:
{{"clips": [{{"title": "catchy title", "startTime": 120, "endTime": 155, "reason": "why this works", "score": 85}}]}}

Rules for the JSON:
- "title": catchy clickbait-style title, max 80 chars
- "startTime": start time in seconds (number, from the timestamps above)
- "endTime": end time in seconds (number), must be 30-60 seconds after startTime
- "reason": 1-2 sentences on why this segment would go viral
- "score": viral potential 1-100

You MUST return exactly 5 clips. No more, no less. Each clip should be from a different part of the transcript. Respond with ONLY the JSON object, nothing else."""


def analyze_transcript_ollama(
    video_title: str,
    transcript: str,
    host: str = "http://localhost:11434",
    model: str = "llama3.1:8b",
) -> List[Dict]:
    """Analyze transcript using local Ollama instance."""
    resp = requests.post(
        f"{host}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(video_title, transcript)},
            ],
            "format": "json",
            "stream": False,
        },
        timeout=600,  # CPU inference can be slow
    )
    resp.raise_for_status()
    text = resp.json()["message"]["content"]
    parsed = json.loads(text)
    arr = parsed if isinstance(parsed, list) else parsed.get("clips", parsed.get("segments", []))
    return _validate_clips(arr)


def analyze_transcript_anthropic(
    video_title: str,
    transcript: str,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
) -> List[Dict]:
    """Analyze transcript using Anthropic API."""
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 2048,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": build_user_prompt(video_title, transcript)},
            ],
        },
        timeout=120,
    )
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"]
    # Extract JSON from response
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON in the response
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
        else:
            raise ValueError(f"Could not parse AI response: {text[:200]}")
    arr = parsed if isinstance(parsed, list) else parsed.get("clips", parsed.get("segments", []))
    return _validate_clips(arr)


def analyze_transcript_oci(
    video_title: str,
    transcript: str,
    compartment_id: str = "",
    region: str = "us-ashburn-1",
    model_id: str = "google.gemini-2.5-flash",
) -> List[Dict]:
    """Analyze transcript using Oracle Cloud GenAI with Instance Principal auth."""
    if not HAS_OCI:
        raise RuntimeError("oci package not installed. Run: pip install oci")

    # Try Instance Principal auth (OCI compute), fall back to API Key auth (local)
    try:
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        config = {}
        if not compartment_id:
            import urllib.request
            req = urllib.request.Request(
                "http://169.254.169.254/opc/v2/instance/",
                headers={"Authorization": "Bearer Oracle"})
            resp = urllib.request.urlopen(req, timeout=5)
            metadata = json.loads(resp.read())
            compartment_id = metadata.get("compartmentId", "")
    except Exception:
        config = oci.config.from_file()
        signer = None
        if not compartment_id:
            compartment_id = config.get("tenancy", "")

    client_kwargs = {
        "config": config,
        "service_endpoint": f"https://inference.generativeai.{region}.oci.oraclecloud.com",
    }
    if signer:
        client_kwargs["signer"] = signer
    client = oci.generative_ai_inference.GenerativeAiInferenceClient(**client_kwargs)

    prompt = SYSTEM_PROMPT + "\n\n" + build_user_prompt(video_title, transcript)

    chat_detail = oci.generative_ai_inference.models.ChatDetails(
        compartment_id=compartment_id,
        serving_mode=oci.generative_ai_inference.models.OnDemandServingMode(
            model_id=model_id
        ),
        chat_request=oci.generative_ai_inference.models.GenericChatRequest(
            api_format="GENERIC",
            messages=[
                oci.generative_ai_inference.models.UserMessage(
                    content=[oci.generative_ai_inference.models.TextContent(text=prompt)]
                )
            ],
            max_tokens=4096,
            temperature=0.7,
        ),
    )

    response = client.chat(chat_detail)
    chat_resp = response.data.chat_response
    text = chat_resp.choices[0].message.content[0].text

    return _parse_clips_response(text)


def _parse_clips_response(text: str) -> List[Dict]:
    """Robustly parse clip JSON from AI response, handling markdown and malformed JSON."""
    import re

    cleaned = text.strip()
    # Remove markdown code blocks
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    cleaned = cleaned.strip()

    # Try direct parse
    try:
        parsed = json.loads(cleaned)
        arr = parsed if isinstance(parsed, list) else parsed.get("clips", parsed.get("segments", []))
        return _validate_clips(arr)
    except json.JSONDecodeError:
        # Try fixing common issues: trailing commas, truncated JSON
        # Remove trailing commas before } or ]
        fixed = re.sub(r',\s*([}\]])', r'\1', cleaned)
        # If JSON is truncated, try to close it
        if fixed.count('[') > fixed.count(']'):
            fixed += ']}'
        if fixed.count('{') > fixed.count('}'):
            fixed += '}'
        try:
            parsed = json.loads(fixed)
            arr = parsed if isinstance(parsed, list) else parsed.get("clips", parsed.get("segments", []))
            return _validate_clips(arr)
        except json.JSONDecodeError:
            pass

    # Try extracting individual clip objects with regex
    clips = []
    # Find all JSON-like objects with the expected fields (allow multiline reason)
    pattern = r'"title"\s*:\s*"([^"]*)"[^}]*?"startTime"\s*:\s*(\d+(?:\.\d+)?)[^}]*?"endTime"\s*:\s*(\d+(?:\.\d+)?)[^}]*?"reason"\s*:\s*"((?:[^"\\]|\\.)*)"\s*[^}]*?"score"\s*:\s*(\d+)'
    matches = re.findall(pattern, cleaned, re.DOTALL)
    for title, start, end, reason, score in matches:
        clips.append({
            "title": title,
            "startTime": float(start),
            "endTime": float(end),
            "reason": reason,
            "score": int(score),
        })

    if clips:
        return _validate_clips(clips)

    raise ValueError(f"Could not parse AI response: {text[:300]}")


def _validate_clips(clips: List[Dict]) -> List[Dict]:
    """Validate and clean clip data."""
    valid = []
    for clip in clips:
        if not all(k in clip for k in ("title", "startTime", "endTime", "score")):
            continue
        duration = clip["endTime"] - clip["startTime"]
        if duration < 15 or duration > 90:
            continue
        clip["score"] = max(1, min(100, int(clip["score"])))
        valid.append(clip)
    return sorted(valid, key=lambda c: c["score"], reverse=True)
