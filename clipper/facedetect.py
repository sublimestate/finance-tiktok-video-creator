"""Detect the primary speaker's face position in a video."""

import json
import subprocess
import tempfile
import os
import cv2
from typing import Dict


def detect_face_in_clip(video_path: str, start_time: float, end_time: float,
                        sample_count: int = 8) -> Dict:
    """Detect face in a specific time range of a video.

    Extracts the clip segment first, then runs face detection on it.
    """
    # Extract the clip segment to a temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(start_time), "-i", video_path,
             "-t", str(end_time - start_time), "-c", "copy", tmp.name],
            capture_output=True, timeout=30,
        )
        return detect_face(tmp.name, sample_count=sample_count)
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


def detect_face(video_path: str, sample_count: int = 10) -> Dict:
    """Detect face position by sampling frames.

    Returns dict with: found, x, y, w, h, videoWidth, videoHeight
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"found": False, "x": 0, "y": 0, "w": 0, "h": 0,
                "videoWidth": 0, "videoHeight": 0}

    video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames <= 0:
        cap.release()
        return {"found": False, "x": video_width // 2, "y": video_height // 2,
                "w": 0, "h": 0, "videoWidth": video_width, "videoHeight": video_height}

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    face_positions = []
    step = max(1, total_frames // sample_count)

    for i in range(0, total_frames, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(50, 50))
        if len(faces) > 0:
            largest = max(faces, key=lambda f: f[2] * f[3])
            x, y, w, h = largest
            face_positions.append((x + w // 2, y + h // 2, w, h))

    cap.release()

    if not face_positions:
        return {"found": False, "x": video_width // 2, "y": video_height // 2,
                "w": 0, "h": 0, "videoWidth": video_width, "videoHeight": video_height}

    avg_x = int(sum(p[0] for p in face_positions) / len(face_positions))
    avg_y = int(sum(p[1] for p in face_positions) / len(face_positions))
    avg_w = int(sum(p[2] for p in face_positions) / len(face_positions))
    avg_h = int(sum(p[3] for p in face_positions) / len(face_positions))

    return {"found": True, "x": avg_x, "y": avg_y, "w": avg_w, "h": avg_h,
            "videoWidth": video_width, "videoHeight": video_height}
