"""Download YouTube videos using yt-dlp."""

import os
import subprocess
from pathlib import Path

# Use local binary if available, otherwise system yt-dlp
_PROJECT_DIR = Path(__file__).parent.parent.resolve()
_LOCAL_YTDLP = str(_PROJECT_DIR / "yt-dlp")
YTDLP_BIN = _LOCAL_YTDLP if os.path.exists(_LOCAL_YTDLP) else "yt-dlp"

# Ensure Deno is in PATH for yt-dlp JS challenge solving
_DENO_PATH = os.path.expanduser("~/.deno/bin")
if _DENO_PATH not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _DENO_PATH + ":" + os.environ.get("PATH", "")


def download_video(video_id: str, output_dir: str, cookies_file: str = "") -> str:
    """Download a YouTube video. Returns the local file path."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = str(Path(output_dir) / f"{video_id}.mp4")

    # Skip if already downloaded
    if Path(output_path).exists() and Path(output_path).stat().st_size > 0:
        print(f"  Video already cached: {output_path}")
        return output_path

    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        YTDLP_BIN,
        "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "-o", output_path,
        "--no-playlist",
    ]
    if cookies_file and Path(cookies_file).exists():
        cmd += ["--cookies", cookies_file]
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr[-500:]}")
    return output_path


def download_from_oci(video_id: str, output_dir: str,
                      bucket: str = "finance-videos",
                      namespace: str = "idtd7ksjim3e") -> str:
    """Download a video from Oracle Object Storage. Returns local file path."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = str(Path(output_dir) / f"{video_id}.mp4")

    if Path(output_path).exists() and Path(output_path).stat().st_size > 0:
        print(f"  Video already cached: {output_path}")
        return output_path

    try:
        import oci
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        os_client = oci.object_storage.ObjectStorageClient(config={}, signer=signer)

        response = os_client.get_object(namespace, bucket, f"{video_id}.mp4")

        with open(output_path, "wb") as f:
            for chunk in response.data.raw.stream(8192):
                f.write(chunk)

        size_mb = Path(output_path).stat().st_size / (1024 * 1024)
        print(f"  Downloaded from OCI: {output_path} ({size_mb:.1f} MB)")
        return output_path
    except Exception as e:
        raise RuntimeError(f"OCI download failed: {e}")
