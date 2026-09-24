#!/bin/bash
# Upload a YouTube video + transcript to Oracle Object Storage for processing
# Usage: ./upload_video.sh <youtube-url>
#
# Prerequisites (install on your laptop):
#   brew install yt-dlp   (or pip install yt-dlp)
#   pip install oci-cli    (or brew install oci-cli)
#   pip install youtube-transcript-api
#
# First-time setup:
#   oci setup config      (follow prompts to set up OCI credentials)

set -e

BUCKET="YOUR_BUCKET_NAME"
NAMESPACE="YOUR_OCI_NAMESPACE"
REGION="us-ashburn-1"

if [ -z "$1" ]; then
    echo "Usage: ./upload_video.sh <youtube-url>"
    echo ""
    echo "Downloads a YouTube video + transcript and uploads to Oracle Object Storage."
    echo "The server can then process it with: python3 clip_video.py <video-id> --skip-download"
    exit 1
fi

URL="$1"

# Extract video ID (works on both macOS and Linux)
VIDEO_ID=$(echo "$URL" | sed -n 's/.*v=\([a-zA-Z0-9_-]\{11\}\).*/\1/p')
if [ -z "$VIDEO_ID" ]; then
    VIDEO_ID=$(echo "$URL" | sed -n 's/.*youtu\.be\/\([a-zA-Z0-9_-]\{11\}\).*/\1/p')
fi
if [ -z "$VIDEO_ID" ]; then
    VIDEO_ID="$URL"  # Assume it's already an ID
fi

echo "Video ID: $VIDEO_ID"
OUTPUT="/tmp/${VIDEO_ID}.mp4"
TRANSCRIPT="/tmp/${VIDEO_ID}_transcript.json"

# Step 1: Download at max quality
echo "=== Downloading video at max quality ==="
yt-dlp -f "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]" \
    --merge-output-format mp4 \
    -o "$OUTPUT" \
    --no-playlist \
    "$URL"

FILE_SIZE=$(du -h "$OUTPUT" | cut -f1)
echo "Downloaded: $OUTPUT ($FILE_SIZE)"

# Step 2: Fetch YouTube transcript
echo "=== Fetching YouTube transcript ==="
python3 -c "
import json
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    items = api.fetch('$VIDEO_ID')
    segments = [{'start': item.start, 'end': item.start + item.duration, 'text': item.text} for item in items]
    with open('$TRANSCRIPT', 'w') as f:
        json.dump(segments, f)
    print(f'Transcript saved: {len(segments)} segments')
except Exception as e:
    print(f'Transcript fetch failed (will use Vosk on server): {e}')
    # Create empty file so we know we tried
    import sys; sys.exit(1)
" 2>&1
TRANSCRIPT_OK=$?

# Step 3: Upload video to Oracle Object Storage
echo "=== Uploading video to Oracle Object Storage ==="
oci os object put \
    --bucket-name "$BUCKET" \
    --namespace "$NAMESPACE" \
    --name "${VIDEO_ID}.mp4" \
    --file "$OUTPUT" \
    --region "$REGION" \
    --no-multipart

# Step 4: Upload transcript if available
if [ $TRANSCRIPT_OK -eq 0 ] && [ -f "$TRANSCRIPT" ]; then
    echo "=== Uploading transcript ==="
    oci os object put \
        --bucket-name "$BUCKET" \
        --namespace "$NAMESPACE" \
        --name "${VIDEO_ID}_transcript.json" \
        --file "$TRANSCRIPT" \
        --region "$REGION" \
        --no-multipart
    echo "Transcript uploaded!"
else
    echo "No transcript available — server will use Vosk (slower)"
fi

echo ""
echo "=== Done! ==="
echo "Video uploaded to: oci://$BUCKET/${VIDEO_ID}.mp4"
if [ $TRANSCRIPT_OK -eq 0 ]; then
    echo "Transcript uploaded to: oci://$BUCKET/${VIDEO_ID}_transcript.json"
fi
echo ""
echo "On the server, run:"
echo "  python3 clip_video.py $VIDEO_ID --ai oci --skip-download --quality preview"
echo ""

# Cleanup
rm -f "$OUTPUT" "$TRANSCRIPT"
echo "Local files cleaned up."
