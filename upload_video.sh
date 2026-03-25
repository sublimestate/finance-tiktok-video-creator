#!/bin/bash
# Upload a YouTube video to Oracle Object Storage for processing
# Usage: ./upload_video.sh <youtube-url>
#
# Prerequisites (install on your laptop):
#   brew install yt-dlp   (or pip install yt-dlp)
#   pip install oci-cli    (or brew install oci-cli)
#
# First-time setup:
#   oci setup config      (follow prompts to set up OCI credentials)

set -e

BUCKET="finance-videos"
NAMESPACE="idtd7ksjim3e"
REGION="us-ashburn-1"

if [ -z "$1" ]; then
    echo "Usage: ./upload_video.sh <youtube-url>"
    echo ""
    echo "Downloads a YouTube video at max quality and uploads to Oracle Object Storage."
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

# Step 1: Download at max quality
echo "=== Downloading video at max quality ==="
yt-dlp -f "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]" \
    --merge-output-format mp4 \
    -o "$OUTPUT" \
    --no-playlist \
    "$URL"

FILE_SIZE=$(du -h "$OUTPUT" | cut -f1)
echo "Downloaded: $OUTPUT ($FILE_SIZE)"

# Step 2: Upload to Oracle Object Storage
echo "=== Uploading to Oracle Object Storage ==="
oci os object put \
    --bucket-name "$BUCKET" \
    --namespace "$NAMESPACE" \
    --name "${VIDEO_ID}.mp4" \
    --file "$OUTPUT" \
    --region "$REGION" \
    --no-multipart

echo ""
echo "=== Done! ==="
echo "Video uploaded to: oci://$BUCKET/${VIDEO_ID}.mp4"
echo ""
echo "On the server, run:"
echo "  python3 clip_video.py $VIDEO_ID --ai oci"
echo ""

# Cleanup
rm -f "$OUTPUT"
echo "Local file cleaned up."
