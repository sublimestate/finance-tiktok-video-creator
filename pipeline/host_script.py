"""AI script generator for host_video.py — produces YAML with host-beat marks.

Separate from quick_video.py's script prompt so this can evolve
independently. Uses the same OCI Gemini 2.5 Flash backend that
clipper/analyze.py uses (see analyze_transcript_oci for the pattern).
"""
import json
import re
from typing import Dict, List, Optional

import yaml

HOST_SCRIPT_SYSTEM_PROMPT = """You are a TikTok finance script writer. Produce a YAML script
of 8-10 scenes for a 25-30 second vertical TikTok video about the given
news headline.

Rules — follow EXACTLY:

1. Total scenes: 8 to 10
2. Each scene has: narration (one short sentence), duration (2-4s), and either:
     visuals: { type: news_video|news_image, query: "search query" }
   OR:
     speaker: host  (and NO visuals field)
3. Mark exactly 2 or 3 scenes as `speaker: host`. Not fewer, not more.
4. Host-beat scenes are 3-5 seconds each, written in first person,
   conversational tone ("Here's the thing", "Watch this", "Trust me").
5. Pick host beats that are interpretive or opinionated — the punchline,
   the "why this matters", the call to action — NOT factual recital.
   Collage scenes carry the facts; host beats carry the perspective.
6. The first AND last scenes should NOT both be host beats. Pick one or
   neither for the bookends.
7. Each scene must stand on its own — do NOT use "as I said" or "in the
   previous scene" because a host beat may degrade to a still portrait
   if rendering fails.

Output ONLY valid YAML. No prose, no markdown fences, no comments.

The YAML schema:

title: "..."
hook:
  text: "HOOK IN ALL CAPS"
  duration: 0.6
  style: bold
scenes:
  - narration: "..."
    duration: 3.0
    visuals: { type: news_image, query: "..." }
  - narration: "Here's the thing — ..."
    duration: 4.0
    speaker: host
"""


def build_host_script_prompt(headline: str, research_text: str = "") -> str:
    """Construct the prompt sent to OCI Gemini.

    The system prompt above lists the rules; this wraps it with the
    headline + research context.
    """
    research_block = f"\n\nResearch context:\n{research_text}\n" if research_text else ""
    return (
        HOST_SCRIPT_SYSTEM_PROMPT
        + f"\n\nHeadline: {headline}{research_block}\n\nProduce the YAML now:"
    )


def _call_oci_gemini(prompt: str) -> str:
    """Send the prompt to OCI Gemini 2.5 Flash and return the raw text.

    Mirrors the auth + call pattern in clipper/analyze.py.
    """
    import oci
    import urllib.request

    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    req = urllib.request.Request(
        "http://169.254.169.254/opc/v2/instance/",
        headers={"Authorization": "Bearer Oracle"},
    )
    cid = json.loads(urllib.request.urlopen(req, timeout=5).read())["compartmentId"]
    client = oci.generative_ai_inference.GenerativeAiInferenceClient(
        config={},
        signer=signer,
        service_endpoint="https://inference.generativeai.us-ashburn-1.oci.oraclecloud.com",
    )
    chat_detail = oci.generative_ai_inference.models.ChatDetails(
        compartment_id=cid,
        serving_mode=oci.generative_ai_inference.models.OnDemandServingMode(
            model_id="google.gemini-2.5-flash"
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
    resp = client.chat(chat_detail)
    return resp.data.chat_response.choices[0].message.content[0].text


def parse_script(yaml_text: str) -> Dict:
    """Parse the AI's YAML response, stripping any markdown fences."""
    cleaned = re.sub(r"^```(?:yaml|yml)?\s*", "", yaml_text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    return yaml.safe_load(cleaned)


def host_beat_indices(script: Dict) -> List[int]:
    """Return the indices of scenes marked `speaker: host`."""
    return [
        i for i, scene in enumerate(script.get("scenes", []))
        if scene.get("speaker") == "host"
    ]


def generate_host_script(headline: str, research_text: str = "") -> Dict:
    """End-to-end: build prompt, call Gemini, parse YAML.

    On parse failure, raises ValueError so the caller can decide whether
    to retry or fall back. Does not catch network errors.
    """
    prompt = build_host_script_prompt(headline, research_text)
    raw = _call_oci_gemini(prompt)
    parsed = parse_script(raw)
    if not parsed or "scenes" not in parsed:
        raise ValueError(f"AI returned unparseable script:\n{raw[:500]}")
    return parsed
