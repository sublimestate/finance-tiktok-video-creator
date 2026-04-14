"""Tests for avatar/runpod.py — RunPodSession context manager.

Mocks both the RunPod REST API (pod create/status/stop) and the inner
pod service (the /render endpoint inside the pod). No real network.
"""
from pathlib import Path

import pytest
import responses

from avatar.runpod import RunPodSession, RunPodError

POD_ID = "pod-fake-123"
POD_HOST = "pod-fake-123.proxy.runpod.net"
RUNPOD_BASE = "https://api.runpod.io/v1"
INNER_BASE = f"https://{POD_HOST}"


@pytest.fixture
def mock_runpod_lifecycle():
    """Stub the create → status (running) → stop sequence."""
    with responses.RequestsMock() as rsps:
        rsps.post(
            f"{RUNPOD_BASE}/pods",
            json={"id": POD_ID, "machineId": "m1"},
            status=200,
        )
        rsps.get(
            f"{RUNPOD_BASE}/pods/{POD_ID}",
            json={
                "id": POD_ID,
                "desiredStatus": "RUNNING",
                "runtime": {
                    "ports": [{"publicPort": 8000, "isIpPublic": True, "ip": POD_HOST}]
                },
            },
            status=200,
        )
        rsps.get(f"{INNER_BASE}/healthz", body="ok", status=200)
        rsps.post(f"{RUNPOD_BASE}/pods/{POD_ID}/stop", json={"id": POD_ID}, status=200)
        yield rsps


def test_session_starts_and_stops_pod(tmp_path: Path, mock_runpod_lifecycle):
    with RunPodSession(image="liveportrait-runpod:0.1.0", api_key="fake") as session:
        assert session.pod_id == POD_ID

    # __exit__ must call /stop. responses raises if any registered call is unused.
    stop_calls = [c for c in mock_runpod_lifecycle.calls if c.request.url.endswith("/stop")]
    assert len(stop_calls) == 1


def test_session_stops_pod_even_on_exception(tmp_path: Path, mock_runpod_lifecycle):
    with pytest.raises(ValueError):
        with RunPodSession(image="liveportrait-runpod:0.1.0", api_key="fake"):
            raise ValueError("boom")

    stop_calls = [c for c in mock_runpod_lifecycle.calls if c.request.url.endswith("/stop")]
    assert len(stop_calls) == 1, "pod must stop even when the body raises"


def test_render_posts_to_inner_service(tmp_path: Path, mock_runpod_lifecycle):
    portrait = tmp_path / "p.png"
    portrait.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFFfake")
    output = tmp_path / "out.mp4"

    fake_video = b"\x00\x00\x00 ftypisom" + b"\x00" * 100
    mock_runpod_lifecycle.post(f"{INNER_BASE}/render", body=fake_video, status=200)

    with RunPodSession(image="liveportrait-runpod:0.1.0", api_key="fake") as session:
        result = session.render(portrait=portrait, audio=audio, output=output)

    assert result == output
    assert output.read_bytes() == fake_video


def test_render_batch_serializes_jobs(tmp_path: Path, mock_runpod_lifecycle):
    portrait = tmp_path / "p.png"
    portrait.write_bytes(b"png")
    a1 = tmp_path / "a1.wav"; a1.write_bytes(b"audio1")
    a2 = tmp_path / "a2.wav"; a2.write_bytes(b"audio2")

    fake_video = b"\x00\x00\x00 ftypisom" + b"\x00" * 100
    mock_runpod_lifecycle.post(f"{INNER_BASE}/render", body=fake_video, status=200)
    mock_runpod_lifecycle.post(f"{INNER_BASE}/render", body=fake_video, status=200)

    with RunPodSession(image="liveportrait-runpod:0.1.0", api_key="fake") as session:
        results = session.render_batch([
            (portrait, a1, tmp_path / "o1.mp4"),
            (portrait, a2, tmp_path / "o2.mp4"),
        ])

    assert len(results) == 2
    assert all(p.exists() for p in results)


def test_failed_pod_create_raises(tmp_path: Path):
    with responses.RequestsMock() as rsps:
        rsps.post(f"{RUNPOD_BASE}/pods", json={"error": "no GPU available"}, status=503)
        with pytest.raises(RunPodError, match="no GPU"):
            with RunPodSession(image="liveportrait-runpod:0.1.0", api_key="fake"):
                pass


def test_render_batch_propagates_partial_failure_and_still_stops_pod(tmp_path: Path):
    """If a mid-batch render fails with non-200, the exception propagates
    and the pod is still stopped via __exit__. This is the cost-safety
    invariant under partial failure."""
    portrait = tmp_path / "p.png"
    portrait.write_bytes(b"png")
    a1 = tmp_path / "a1.wav"; a1.write_bytes(b"audio1")
    a2 = tmp_path / "a2.wav"; a2.write_bytes(b"audio2")
    fake_video = b"\x00\x00\x00 ftypisom" + b"\x00" * 100

    with responses.RequestsMock() as rsps:
        rsps.post(
            f"{RUNPOD_BASE}/pods",
            json={"id": POD_ID, "machineId": "m1"}, status=200,
        )
        rsps.get(
            f"{RUNPOD_BASE}/pods/{POD_ID}",
            json={
                "id": POD_ID,
                "desiredStatus": "RUNNING",
                "runtime": {
                    "ports": [{"publicPort": 8000, "isIpPublic": True, "ip": POD_HOST}]
                },
            },
            status=200,
        )
        rsps.get(f"{INNER_BASE}/healthz", body="ok", status=200)
        # First render succeeds, second fails with 500
        rsps.post(f"{INNER_BASE}/render", body=fake_video, status=200)
        rsps.post(f"{INNER_BASE}/render", body="liveportrait crashed", status=500)
        rsps.post(f"{RUNPOD_BASE}/pods/{POD_ID}/stop", json={"id": POD_ID}, status=200)

        with pytest.raises(RunPodError, match="render failed"):
            with RunPodSession(image="liveportrait-runpod:0.1.0", api_key="fake") as session:
                session.render_batch([
                    (portrait, a1, tmp_path / "o1.mp4"),
                    (portrait, a2, tmp_path / "o2.mp4"),
                ])

        # Verify the stop endpoint was called even though the batch raised
        stop_calls = [c for c in rsps.calls if c.request.url.endswith("/stop")]
        assert len(stop_calls) == 1, "pod must stop even when mid-batch render fails"


def test_session_appends_to_billing_log(tmp_path: Path, mock_runpod_lifecycle, monkeypatch):
    monkeypatch.setenv("RUNPOD_BILLING_LOG", str(tmp_path / "billing.log"))
    with RunPodSession(image="liveportrait-runpod:0.1.0", api_key="fake"):
        pass
    log = (tmp_path / "billing.log").read_text()
    # Format: "<isodate>\t<seconds>\t<cost_estimate>\n"
    assert "\t" in log
    parts = log.strip().split("\t")
    assert len(parts) == 3
    seconds = float(parts[1])
    assert seconds >= 0


def test_session_warns_if_exceeds_max_seconds(
    tmp_path: Path, mock_runpod_lifecycle, monkeypatch, capsys
):
    monkeypatch.setenv("MAX_RUNPOD_SECONDS_PER_RUN", "0")  # any session exceeds this
    monkeypatch.setenv("RUNPOD_BILLING_LOG", str(tmp_path / "billing.log"))

    with RunPodSession(image="liveportrait-runpod:0.1.0", api_key="fake"):
        pass

    out = capsys.readouterr().out
    assert "exceeded" in out.lower() or "warning" in out.lower()
