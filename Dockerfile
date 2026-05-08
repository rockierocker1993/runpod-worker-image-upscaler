FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

# ---------------------------------------------------------------------------
# CUDA / PyTorch performance environment variables
# ---------------------------------------------------------------------------
# Lazy-load CUDA modules → faster cold start for serverless
ENV CUDA_MODULE_LOADING=LAZY
# Reduce VRAM fragmentation between serverless jobs
ENV PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
# Disable Python output buffering for cleaner RunPod logs
ENV PYTHONUNBUFFERED=1
# Prevent interactive prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Python 3.10 + system dependencies for Pillow / OpenCV used by Real-ESRGAN
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3.10-dev \
    libgl1 \
    libglib2.0-0 \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3 \
    && ln -sf /usr/bin/pip3 /usr/bin/pip \
    && rm -rf /var/lib/apt/lists/*

# Pre-install torch for CUDA 12.1 so basicsr setup.py does not pull in
# conflicting cuda-toolkit/nvidia-cublas setup_requires at build time.
RUN python3 -m pip install --no-cache-dir \
    torch==2.3.1 torchvision==0.18.1 \
    --index-url https://download.pytorch.org/whl/cu121

# Install basicsr with --no-build-isolation to skip setup_requires CUDA conflict,
# then install the remaining dependencies normally.
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --no-build-isolation basicsr \
 && python3 -m pip install --no-cache-dir -r requirements.txt \
 && sed -i 's/from torchvision.transforms.functional_tensor import rgb_to_grayscale/from torchvision.transforms.functional import rgb_to_grayscale/' \
    /usr/local/lib/python3.10/dist-packages/basicsr/data/degradations.py

# Application code
COPY . .

CMD ["python3", "-u", "main.py"]
