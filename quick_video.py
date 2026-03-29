#!/usr/bin/env python3
"""Quick Video Generator — Turn a headline into a TikTok video in minutes."""

import argparse
import json
import os
import sys
import yaml
import requests
from pathlib import Path


def load_config(config_path: str = "config.yaml") -> dict:
    if not os.path.exists(config_path):
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def research_topic(topic: str) -> str:
    """Search the web for current data on the topic."""
    config = load_config()
    serpapi_key = config.get("api_keys", {}).get("serpapi_key", "")
    if not serpapi_key:
        return ""

    try:
        resp = requests.get(
            "https://serpapi.com/search.json",
            params={"api_key": serpapi_key, "q": topic + " latest data 2026", "num": 5},
            timeout=15,
        )
        if resp.status_code != 200:
            return ""
        results = resp.json().get("organic_results", [])
        context = []
        for r in results[:3]:
            snippet = r.get("snippet", "")
            if snippet:
                context.append(snippet)
        return "\n".join(context)
    except Exception:
        return ""


def generate_script(topic: str, context: str = "") -> dict:
    """Use OCI GenAI to generate a YAML script from a topic."""
    import oci
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()

    # Get compartment from instance metadata
    import urllib.request
    req = urllib.request.Request(
        "http://169.254.169.254/opc/v2/instance/",
        headers={"Authorization": "Bearer Oracle"})
    resp = urllib.request.urlopen(req, timeout=5)
    compartment = json.loads(resp.read()).get("compartmentId", "")

    client = oci.generative_ai_inference.GenerativeAiInferenceClient(
        config={}, signer=signer,
        service_endpoint="https://inference.generativeai.us-ashburn-1.oci.oraclecloud.com",
    )

    prompt = f"""You are a TikTok finance content creator. Create a fast-paced video script about this topic:

TOPIC: {topic}

{"CURRENT DATA/CONTEXT:" + chr(10) + context if context else ""}

Requirements:
- 8 scenes, each 2-3 seconds of narration (SHORT punchy sentences)
- Total video should be 20-30 seconds
- First scene must be a STRONG HOOK that makes people stop scrolling
- Last scene must be a CTA ("Follow for more")
- Mix of video clip searches and news image searches for visuals
- Bold text overlays on every scene
- Use actual numbers and data when available

HOOK RULES (most important part):
- The hook text must create URGENCY or CURIOSITY
- Use one of these proven patterns:
  * Numbers: "YOUR MONEY LOST $2,400 TODAY"
  * Fear: "THIS WILL DESTROY YOUR SAVINGS"
  * Curiosity gap: "NOBODY IS TALKING ABOUT THIS"
  * Contrarian: "STOP INVESTING RIGHT NOW"
  * Breaking: "BREAKING: MARKETS JUST CRASHED"
- Keep it under 6 words, ALL CAPS
- The hook style should be "glitch" for urgency or "bold" for breaking news
- The first narration scene should IMMEDIATELY expand on the hook with a shocking stat or claim

Return ONLY valid YAML matching this exact format (no markdown, no explanation):

title: "catchy title"
voice: "adam"
character: false
hook:
  text: "HOOK IN CAPS - MAX 6 WORDS"
  duration: 1.2
  style: glitch
scenes:
  - narration: "short punchy sentence"
    duration: 2.5
    visuals:
      type: news_video
      query: "relevant video search query"
    text_overlay:
      content: "Key Point"
      style: title
      position: center
  - narration: "next point"
    duration: 2.5
    visuals:
      type: news_image
      query: "relevant image search"
    text_overlay:
      content: "Another Point"
      style: lower_third
      position: bottom"""

    chat_detail = oci.generative_ai_inference.models.ChatDetails(
        compartment_id=compartment,
        serving_mode=oci.generative_ai_inference.models.OnDemandServingMode(
            model_id="xai.grok-3-mini-fast"
        ),
        chat_request=oci.generative_ai_inference.models.GenericChatRequest(
            api_format="GENERIC",
            messages=[
                oci.generative_ai_inference.models.UserMessage(
                    content=[oci.generative_ai_inference.models.TextContent(text=prompt)]
                )
            ],
            max_tokens=2048,
            temperature=0.7,
        ),
    )

    response = client.chat(chat_detail)
    text = response.data.chat_response.choices[0].message.content[0].text

    # Clean up response — remove markdown code blocks
    import re
    text = re.sub(r'^```(?:yaml)?\s*', '', text.strip())
    text = re.sub(r'\s*```$', '', text.strip())

    return yaml.safe_load(text)


def main():
    parser = argparse.ArgumentParser(description="Generate a TikTok video from a headline")
    parser.add_argument("topic", nargs="+", help="The topic or headline")
    parser.add_argument("--config", "-c", default="config.yaml", help="Config file path")
    parser.add_argument("--voice", default="adam", help="TTS voice name")
    args = parser.parse_args()

    topic = " ".join(args.topic)
    project_dir = Path(__file__).parent.resolve()

    print(f"Topic: {topic}")
    print("=" * 50)

    # Step 1: Research
    print("STEP 1: Researching topic...")
    context = research_topic(topic)
    if context:
        print(f"  Found {len(context)} chars of context")
    else:
        print("  No additional context found, using topic as-is")

    # Step 2: Generate script
    print("STEP 2: Generating script with AI...")
    script_data = generate_script(topic, context)
    script_data["voice"] = args.voice

    # Save script
    from slugify import slugify
    script_name = slugify(script_data.get("title", topic))[:40]
    script_path = str(project_dir / "scripts" / f"{script_name}.yaml")
    with open(script_path, "w") as f:
        yaml.dump(script_data, f, default_flow_style=False, allow_unicode=True)
    print(f"  Script saved: {script_path}")
    print(f"  Title: {script_data.get('title', '?')}")
    print(f"  Scenes: {len(script_data.get('scenes', []))}")

    # Step 3: Render video
    print("STEP 3: Rendering video...")
    print("=" * 50)

    # Import and run the create_video pipeline
    os.system(f"cd {project_dir} && python3 create_video.py {script_path}")

    output_name = slugify(script_data.get("title", topic))
    output_path = str(project_dir / "output" / f"{output_name}.mp4")
    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"\nDone! {output_path} ({size_mb:.1f} MB)")
    else:
        print(f"\nVideo may be at: {project_dir / 'output' / '*.mp4'}")


if __name__ == "__main__":
    main()
