"""OCI Speech AI transcription — cloud-based, accurate, with word-level timestamps."""

import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import List, Dict, Optional

try:
    import oci
    HAS_OCI = True
except ImportError:
    HAS_OCI = False

BUCKET = "finance-videos"
NAMESPACE = "idtd7ksjim3e"


def _get_compartment_id() -> str:
    import urllib.request
    req = urllib.request.Request(
        "http://169.254.169.254/opc/v2/instance/",
        headers={"Authorization": "Bearer Oracle"})
    resp = urllib.request.urlopen(req, timeout=5)
    return json.loads(resp.read())["compartmentId"]


def transcribe_clip_oci(
    video_path: str,
    start_time: float,
    end_time: float,
    region: str = "us-ashburn-1",
) -> List[Dict]:
    """Transcribe a clip using OCI Speech AI with word-level timestamps.

    Returns list of {"word": str, "start": float, "end": float} (0-based).
    """
    if not HAS_OCI:
        return []

    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    os_client = oci.object_storage.ObjectStorageClient(config={}, signer=signer)
    speech_client = oci.ai_speech.AIServiceSpeechClient(config={}, signer=signer)
    compartment_id = _get_compartment_id()

    # Extract audio for this clip
    duration = end_time - start_time
    tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_wav.close()

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(start_time), "-i", video_path,
             "-t", str(duration), "-ar", "16000", "-ac", "1", "-f", "wav",
             tmp_wav.name],
            capture_output=True, timeout=max(60, int(duration / 5)),
        )

        # Upload audio to OCI Object Storage. uuid suffix avoids collisions
        # when multiple parallel prep threads call this in the same second.
        obj_name = f"temp_speech_{os.getpid()}_{int(time.time())}_{uuid.uuid4().hex[:8]}.wav"
        with open(tmp_wav.name, "rb") as f:
            os_client.put_object(NAMESPACE, BUCKET, obj_name, f)

        # Create transcription job
        job_details = oci.ai_speech.models.CreateTranscriptionJobDetails(
            compartment_id=compartment_id,
            display_name=f"clip-{int(start_time)}-{int(end_time)}",
            model_details=oci.ai_speech.models.TranscriptionModelDetails(
                model_type="WHISPER_MEDIUM",
                domain="GENERIC",
                language_code="en",
            ),
            input_location=oci.ai_speech.models.ObjectListInlineInputLocation(
                location_type="OBJECT_LIST_INLINE_INPUT_LOCATION",
                object_locations=[
                    oci.ai_speech.models.ObjectLocation(
                        namespace_name=NAMESPACE,
                        bucket_name=BUCKET,
                        object_names=[obj_name],
                    )
                ],
            ),
            output_location=oci.ai_speech.models.OutputLocation(
                namespace_name=NAMESPACE,
                bucket_name=BUCKET,
                prefix=f"speech_output/{int(time.time())}_{uuid.uuid4().hex[:8]}/",
            ),
        )

        job = speech_client.create_transcription_job(job_details)
        job_id = job.data.id

        # Wait for completion (poll every 5s, max 3 min)
        for _ in range(36):
            status = speech_client.get_transcription_job(job_id)
            state = status.data.lifecycle_state
            if state == "SUCCEEDED":
                break
            elif state in ("FAILED", "CANCELED"):
                return []
            time.sleep(5)
        else:
            return []

        # Get results
        output_prefix = f"speech_output/{int(time.time() - 180)}/"
        objects = os_client.list_objects(NAMESPACE, BUCKET, prefix="speech_output/")
        result_obj = None
        for o in objects.data.objects:
            if job_id.split(".")[-1] in o.name and o.name.endswith(".json"):
                result_obj = o.name
                break

        if not result_obj:
            # Search by job ID in the output prefix
            tasks = speech_client.list_transcription_tasks(job_id)
            for task in tasks.data.items:
                if task.lifecycle_state == "SUCCEEDED":
                    # Find output file
                    objects = os_client.list_objects(NAMESPACE, BUCKET, prefix="speech_output/")
                    for o in objects.data.objects:
                        if o.name.endswith(".json") and obj_name.replace(".wav", "") in o.name:
                            result_obj = o.name
                            break

        if not result_obj:
            return []

        obj = os_client.get_object(NAMESPACE, BUCKET, result_obj)
        data = json.loads(obj.data.content.decode())
        tokens = data["transcriptions"][0]["tokens"]

        # Convert to our word format
        words = []
        for tok in tokens:
            start = float(tok["startTime"].replace("s", ""))
            end = float(tok["endTime"].replace("s", ""))
            if end <= start:
                end = start + 0.1
            word = tok["token"].rstrip(".,!?;:")
            if word:
                words.append({"word": word, "start": start, "end": end})

        # Cleanup: delete temp audio and output
        try:
            os_client.delete_object(NAMESPACE, BUCKET, obj_name)
            os_client.delete_object(NAMESPACE, BUCKET, result_obj)
        except Exception:
            pass

        return words

    except Exception:
        return []
    finally:
        if os.path.exists(tmp_wav.name):
            os.unlink(tmp_wav.name)
