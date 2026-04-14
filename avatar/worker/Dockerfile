FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    LIVEPORTRAIT_DIR=/opt/LivePortrait

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip git ffmpeg ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

# Clone LivePortrait at a pinned commit so builds are reproducible.
RUN git clone https://github.com/KwaiVGI/LivePortrait.git ${LIVEPORTRAIT_DIR} && \
    cd ${LIVEPORTRAIT_DIR} && \
    git checkout 9b7e9d4

WORKDIR ${LIVEPORTRAIT_DIR}
RUN pip3 install --no-cache-dir -r requirements.txt

# Bake the model weights into the image so cold start doesn't pay download cost.
# These commands match the LivePortrait README's "download weights" step.
RUN python3 -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='KwaiVGI/LivePortrait', local_dir='${LIVEPORTRAIT_DIR}/pretrained_weights')"

# Inner server
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY server.py .

EXPOSE 8000
CMD ["python3", "server.py"]
