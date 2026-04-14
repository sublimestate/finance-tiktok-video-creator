"""Detect burned-in captions in video frames using OpenCV."""

import subprocess
import tempfile
import os
import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


def has_burned_captions(video_path: str, start_time: float, num_samples: int = 5) -> bool:
    # Disabled: too many false positives. Use --no-captions flag manually instead.
    return False
    """Check if a video segment has burned-in captions.

    Samples frames from the lower third and looks for high-contrast
    text-like regions that appear consistently across frames.
    """
    if not HAS_CV2:
        return False

    tmp_dir = tempfile.mkdtemp()
    try:
        # Extract sample frames spread across the clip
        for i in range(num_samples):
            t = start_time + 3 + i * 5  # skip first 3s, sample every 5s
            out_path = os.path.join(tmp_dir, f"frame_{i}.png")
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(t), "-i", video_path,
                 "-frames:v", "1", "-q:v", "2", out_path],
                capture_output=True, timeout=10,
            )

        # Analyze frames for text in the lower portion
        text_detected_count = 0
        for i in range(num_samples):
            frame_path = os.path.join(tmp_dir, f"frame_{i}.png")
            if not os.path.exists(frame_path):
                continue

            img = cv2.imread(frame_path)
            if img is None:
                continue

            h, w = img.shape[:2]

            # Focus on bottom 40% of the frame (captions can be in lower-center)
            bottom = img[int(h * 0.6):, :]

            # Convert to grayscale and HSV for detecting colored text
            gray = cv2.cvtColor(bottom, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(bottom, cv2.COLOR_BGR2HSV)

            # Edge detection to find text-like regions
            edges = cv2.Canny(gray, 80, 180)
            edge_density = np.sum(edges > 0) / edges.size

            # Check for bright text (white, yellow, or other bright colors)
            _, thresh_bright = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
            bright_ratio = np.sum(thresh_bright > 0) / thresh_bright.size

            # Check for saturated bright colors (yellow/green captions)
            sat_mask = hsv[:, :, 1] > 100  # saturated
            val_mask = hsv[:, :, 2] > 180  # bright
            colored_text_ratio = np.sum(sat_mask & val_mask) / sat_mask.size

            # Text detected if: edges + bright pixels, OR colorful bright text
            has_text = (edge_density > 0.02 and bright_ratio > 0.01) or colored_text_ratio > 0.01
            if has_text:
                text_detected_count += 1

        # If text detected in majority of frames, likely has burned captions
        return text_detected_count >= (num_samples * 0.6)

    except Exception:
        return False
    finally:
        # Cleanup
        for f in os.listdir(tmp_dir):
            os.unlink(os.path.join(tmp_dir, f))
        os.rmdir(tmp_dir)
