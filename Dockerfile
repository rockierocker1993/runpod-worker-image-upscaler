FROM runpod/base:0.6.2-cuda12.1.0

WORKDIR /app

# System dependencies for Pillow / OpenCV used by Real-ESRGAN
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
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

# Copy model files to /models directory
COPY models/ /models/

# Application code
COPY . .

CMD ["python3", "-u", "main.py"]
