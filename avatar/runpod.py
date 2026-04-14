"""RunPod Pods REST client + inner-service caller.

Used as a context manager so pod teardown is guaranteed even on Python
exception — the only safety net against orphaned $0.34/hr billing.
"""
import os
import time
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

import requests

API_BASE = "https://api.runpod.io/v1"
DEFAULT_GPU_TYPE = "NVIDIA RTX A5000"  # A10-class, change to "NVIDIA A10" or similar per RunPod naming
POD_BOOT_TIMEOUT_SEC = 180
POD_HEALTH_TIMEOUT_SEC = 120
RENDER_TIMEOUT_SEC = 300
A10_HOURLY_USD = 0.34  # RunPod community A10 — update if pricing changes
DEFAULT_MAX_SECONDS_PER_RUN = 600  # $0.057 at A10 rates


class RunPodError(RuntimeError):
    pass


class RunPodSession:
    """Spin up a pod, render N cutaways on it, tear it down.

    Single pod per video — render_batch keeps the warm pod busy for all
    cutaways before stopping, so we pay the boot cost once.

    Always use as a context manager:

        with RunPodSession(image="liveportrait-runpod:0.1.0") as pod:
            cutaways = pod.render_batch(jobs)
    """

    def __init__(
        self,
        image: str,
        api_key: Optional[str] = None,
        gpu_type: str = DEFAULT_GPU_TYPE,
    ):
        self.image = image
        self.gpu_type = gpu_type
        self.api_key = api_key or os.environ.get("RUNPOD_API_KEY", "")
        if not self.api_key:
            raise RunPodError("RUNPOD_API_KEY not set")
        self.pod_id: Optional[str] = None
        self.inner_base: Optional[str] = None
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {self.api_key}"

    # --- Lifecycle ---

    def __enter__(self) -> "RunPodSession":
        self._started_at = time.monotonic()
        self._create_pod()
        try:
            self._wait_for_running()
            self._wait_for_inner_healthy()
        except Exception:
            # Clean up the pod we just allocated if anything in startup fails
            self._stop_pod_safely()
            self._record_billing()
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop_pod_safely()
        self._record_billing()

    # --- Public API ---

    def render(self, portrait: Path, audio: Path, output: Path) -> Path:
        """Submit one (portrait, audio) job and write the result to output."""
        if not self.inner_base:
            raise RunPodError("Pod not running")
        with open(portrait, "rb") as fp, open(audio, "rb") as fa:
            resp = requests.post(
                f"{self.inner_base}/render",
                files={"portrait": fp, "audio": fa},
                timeout=RENDER_TIMEOUT_SEC,
            )
        if resp.status_code != 200:
            raise RunPodError(f"render failed ({resp.status_code}): {resp.text[:200]}")
        output.write_bytes(resp.content)
        return output

    def render_batch(
        self, jobs: List[Tuple[Path, Path, Path]]
    ) -> List[Path]:
        """Render a list of (portrait, audio, output) jobs in serial on this pod.

        Serial keeps the inner Flask service simple — LivePortrait is
        GPU-bound so concurrent requests would just queue at the GPU anyway.
        """
        results: List[Path] = []
        for portrait, audio, output in jobs:
            results.append(self.render(portrait, audio, output))
        return results

    # --- Internals ---

    def _create_pod(self) -> None:
        resp = self._session.post(
            f"{API_BASE}/pods",
            json={
                "image": self.image,
                "gpuType": self.gpu_type,
                "ports": "8000/http",
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            try:
                err = resp.json().get("error", resp.text)
            except Exception:
                err = resp.text
            raise RunPodError(f"pod create failed: {err}")
        data = resp.json()
        self.pod_id = data["id"]

    def _wait_for_running(self) -> None:
        """Poll RunPod's API until the pod reports RUNNING and exposes a public URL."""
        deadline = time.monotonic() + POD_BOOT_TIMEOUT_SEC
        while time.monotonic() < deadline:
            resp = self._session.get(f"{API_BASE}/pods/{self.pod_id}", timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("desiredStatus") == "RUNNING":
                    runtime = data.get("runtime") or {}
                    ports = runtime.get("ports") or []
                    for port in ports:
                        if port.get("publicPort") == 8000:
                            host = port.get("ip") or port.get("host")
                            if host:
                                self.inner_base = f"https://{host}"
                                return
            time.sleep(3)
        raise RunPodError(f"pod {self.pod_id} did not boot within {POD_BOOT_TIMEOUT_SEC}s")

    def _wait_for_inner_healthy(self) -> None:
        """Poll the pod's inner /healthz until the LivePortrait model is loaded.

        Critical: RunPod's API is eventually consistent. The pod can report
        RUNNING before the inner service is actually accepting requests.
        """
        deadline = time.monotonic() + POD_HEALTH_TIMEOUT_SEC
        while time.monotonic() < deadline:
            try:
                resp = requests.get(f"{self.inner_base}/healthz", timeout=10)
                if resp.status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(3)
        raise RunPodError(f"pod {self.pod_id} inner service never reported healthy")

    def _record_billing(self) -> None:
        if not getattr(self, "_started_at", None):
            return
        elapsed = time.monotonic() - self._started_at
        cost = elapsed / 3600.0 * A10_HOURLY_USD
        max_seconds = float(os.environ.get(
            "MAX_RUNPOD_SECONDS_PER_RUN", DEFAULT_MAX_SECONDS_PER_RUN
        ))
        if elapsed > max_seconds:
            print(
                f"WARNING: RunPod session exceeded MAX_RUNPOD_SECONDS_PER_RUN "
                f"({elapsed:.0f}s > {max_seconds:.0f}s, est ${cost:.3f})"
            )
        log_path = os.environ.get(
            "RUNPOD_BILLING_LOG", "data/avatar/billing.log"
        )
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a") as f:
                f.write(f"{date.today().isoformat()}\t{elapsed:.1f}\t{cost:.4f}\n")
        except OSError:
            pass  # Billing log is best-effort

    def _stop_pod_safely(self) -> None:
        if not self.pod_id:
            return
        try:
            self._session.post(
                f"{API_BASE}/pods/{self.pod_id}/stop", timeout=30
            )
        except Exception:
            # Last-ditch: don't raise during teardown. Log and move on.
            print(f"WARNING: failed to stop pod {self.pod_id} — verify in RunPod console!")
        finally:
            self.pod_id = None
            self.inner_base = None
