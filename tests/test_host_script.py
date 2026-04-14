"""Tests for pipeline/host_script.py — host-beat script generator.

The OCI GenAI call is mocked. We test the prompt and the parsing logic.
"""
from unittest.mock import MagicMock, patch

import pytest

from pipeline import host_script


def test_prompt_contains_required_rules():
    prompt = host_script.build_host_script_prompt("Oil prices crash 5%")
    must_have = [
        "speaker: host",
        "exactly 2 or 3",
        "first person",
        "interpretive",
        "stand on its own",
    ]
    for s in must_have:
        assert s in prompt, f"missing rule: {s}"


def test_parse_script_extracts_host_beat_indices():
    yaml_text = """
title: Test
hook: { text: TEST, duration: 0.6, style: bold }
scenes:
  - narration: "Scene one"
    duration: 3.0
    visuals: { type: news_image, query: foo }
  - narration: "Here's the thing"
    duration: 4.0
    speaker: host
  - narration: "Scene three"
    duration: 3.0
    visuals: { type: news_image, query: bar }
  - narration: "Trust me"
    duration: 4.0
    speaker: host
"""
    parsed = host_script.parse_script(yaml_text)
    assert host_script.host_beat_indices(parsed) == [1, 3]


def test_generate_script_falls_back_to_collage_on_zero_host_beats():
    """If the AI returns 0 host beats, the caller should know — the
    consumer (host_video.py) downgrades to a plain collage video in
    that case rather than calling RunPod for nothing."""
    yaml_text = """
title: Test
hook: { text: TEST, duration: 0.6, style: bold }
scenes:
  - narration: "Only scene"
    duration: 3.0
    visuals: { type: news_image, query: foo }
"""
    parsed = host_script.parse_script(yaml_text)
    assert host_script.host_beat_indices(parsed) == []


def test_generate_script_uses_oci_gemini():
    fake_yaml = """
title: Generated
hook: { text: G, duration: 0.6, style: bold }
scenes:
  - narration: "x"
    duration: 3.0
    visuals: { type: news_image, query: x }
  - narration: "Here's the thing"
    duration: 4.0
    speaker: host
"""
    with patch.object(host_script, "_call_oci_gemini", return_value=fake_yaml):
        result = host_script.generate_host_script("Test headline", research_text="...")
    assert result["title"] == "Generated"
    assert host_script.host_beat_indices(result) == [1]
