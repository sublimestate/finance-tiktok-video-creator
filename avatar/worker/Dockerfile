FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    MUSETALK_DIR=/opt/MuseTalk \
    PATH="/opt/conda/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip git ffmpeg ca-certificates wget curl \
    && rm -rf /var/lib/apt/lists/*

# MuseTalk pins to Python 3.10 (mmcv/chumpy don't build on 3.12).
# Install miniconda so we get a clean 3.10 env without fighting apt.
RUN curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh && \
    bash /tmp/miniconda.sh -b -p /opt/conda && \
    rm /tmp/miniconda.sh && \
    /opt/conda/bin/conda install -n base -c conda-forge python=3.10 -y && \
    /opt/conda/bin/conda clean -afy

# Clone MuseTalk (no pinned commit — repo is stable, validated against
# master on 2026-04-14)
RUN git clone https://github.com/TMElyralab/MuseTalk.git ${MUSETALK_DIR}

WORKDIR ${MUSETALK_DIR}

# torch matching CUDA 11.8 (mmcv==2.1.0 hard-requires torch 2.0.x)
RUN pip install --no-cache-dir \
        torch==2.0.1+cu118 torchvision==0.15.2+cu118 \
        --index-url https://download.pytorch.org/whl/cu118

# MuseTalk Python deps + edge-tts + huggingface CLI + gdown for weights.
# numpy pinned to <1.24 because mmcv/mmpose expect np.int/np.float.
RUN pip install --no-cache-dir \
        "diffusers==0.30.2" \
        "accelerate==0.28.0" \
        "transformers==4.39.2" \
        "huggingface_hub==0.30.2" \
        "omegaconf" \
        "einops==0.8.1" \
        "opencv-python==4.9.0.80" \
        "soundfile==0.12.1" \
        "librosa==0.11.0" \
        "ffmpeg-python" \
        "imageio[ffmpeg]" \
        "numpy==1.23.5" \
        "setuptools<70" \
        "huggingface_hub[cli]" \
        gdown openmim

# chumpy needs --no-build-isolation on modern pip and is pulled in by
# mmpose. Install the github fork which patches a Python 3.10 issue.
RUN pip install --no-cache-dir --no-build-isolation \
        git+https://github.com/mattloper/chumpy.git

# mmpose ecosystem via mim (resolves mmcv/mmdet/mmengine versions).
RUN mim install --no-cache-dir "mmengine" "mmcv==2.1.0" "mmdet==3.2.0" "mmpose==1.3.1"

# Bake all the model weights into the image. Cold start on RunPod is
# already ~60-90s for the pod itself; we can't afford another 5-10 min
# for weights download on every boot.
RUN mkdir -p models/musetalk models/musetalkV15 models/sd-vae models/whisper \
             models/dwpose models/face-parse-bisent models/syncnet && \
    huggingface-cli download TMElyralab/MuseTalk \
        --local-dir models \
        --include "musetalkV15/musetalk.json" "musetalkV15/unet.pth" && \
    huggingface-cli download stabilityai/sd-vae-ft-mse \
        --local-dir models/sd-vae \
        --include "config.json" "diffusion_pytorch_model.bin" && \
    huggingface-cli download openai/whisper-tiny \
        --local-dir models/whisper && \
    huggingface-cli download yzd-v/DWPose \
        --local-dir models/dwpose \
        --include "dw-ll_ucoco_384.pth" && \
    huggingface-cli download ByteDance/LatentSync \
        --local-dir models/syncnet \
        --include "latentsync_syncnet.pt" && \
    gdown "https://drive.google.com/uc?id=154JgKpzCPW82qINcVieuPH3fZ2e0P812" \
        -O models/face-parse-bisent/79999_iter.pth && \
    curl -fsSL https://download.pytorch.org/models/resnet18-5c106cde.pth \
        -o models/face-parse-bisent/resnet18-5c106cde.pth

# s3fd face detection weights are fetched on first inference call.
# Pre-fetch them here so the first /render doesn't do cold-start disk I/O.
RUN mkdir -p /root/.cache/torch/hub/checkpoints && \
    curl -fsSL https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth \
        -o /root/.cache/torch/hub/checkpoints/s3fd-619a316812.pth

# Inner Flask server on top of the MuseTalk env.
RUN pip install --no-cache-dir flask==3.0.3

COPY server.py /app/server.py

EXPOSE 8000
CMD ["python", "/app/server.py"]
