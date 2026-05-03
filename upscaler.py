"""
Real-ESRGAN Image Upscaler.
"""
import os
import logging
import numpy as np
import torch
from PIL import Image
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer

logger = logging.getLogger("runpod-upscaler")

# ---------------------------------------------------------------------------
# CUDA performance flags — set once at import time
# ---------------------------------------------------------------------------
_CUDA_AVAILABLE = torch.cuda.is_available()
if _CUDA_AVAILABLE:
    # Let cuDNN auto-select the fastest conv algorithm for each input shape
    torch.backends.cudnn.benchmark = True
    torch.backends.cudnn.deterministic = False
    # TF32: ~3x faster than FP32 on Ampere (A100, A40, RTX 30xx+)
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    logger.info(
        "CUDA device: %s | TF32: enabled | cuDNN benchmark: enabled | FP16 half: enabled",
        torch.cuda.get_device_name(0),
    )
else:
    logger.warning("No CUDA device found — running on CPU (slow)")


class ImageUpscaler:
    """
    Real-ESRGAN image upscaler.
    Mendukung scale 2x dan 4x.
    """

    # Tile size from env; 0 = no tiling (fastest for small images, risks OOM on large ones)
    _TILE_SIZE = int(os.environ.get("UPSCALER_TILE_SIZE", "0"))

    MODEL_CONFIGS = {
        2: {
            "name": "RealESRGAN_x2plus",
            "path": os.environ.get("MODEL_2X_PATH", "/models/RealESRGAN_x2plus.pth"),
            "num_block": 23,
        },
        4: {
            "name": "RealESRGAN_x4plus",
            "path": os.environ.get("MODEL_4X_PATH", "/models/RealESRGAN_x4plus.pth"),
            "num_block": 23,
        },
    }

    def __init__(self):
        """Initialize upscaler dengan empty cache."""
        self._cache = {}

    def _load_model(self, scale: int) -> RealESRGANer:
        """Load dan cache model untuk scale tertentu."""
        if scale not in self._cache:
            if scale not in self.MODEL_CONFIGS:
                raise ValueError(f"Unsupported scale: {scale}. Must be {list(self.MODEL_CONFIGS.keys())}")

            cfg = self.MODEL_CONFIGS[scale]

            if not os.path.exists(cfg["path"]):
                raise FileNotFoundError(f"Model file not found: {cfg['path']}")

            model = RRDBNet(
                num_in_ch=3,
                num_out_ch=3,
                num_feat=64,
                num_block=cfg["num_block"],
                num_grow_ch=32,
                scale=scale,
            )

            self._cache[scale] = RealESRGANer(
                scale=scale,
                model_path=cfg["path"],
                model=model,
                tile=self._TILE_SIZE,
                tile_pad=10,
                pre_pad=0,
                # FP16: ~2x faster and ~50% less VRAM on CUDA GPUs
                half=_CUDA_AVAILABLE,
            )
            logger.info("Loaded %s model for scale %sx (half=%s)", cfg["name"], scale, _CUDA_AVAILABLE)

        return self._cache[scale]

    def upscale(self, image: Image.Image, scale: int = 4) -> Image.Image:
        """
        Upscale image dengan scale factor tertentu.

        Args:
            image: Input PIL Image
            scale: Scale factor (2 atau 4)

        Returns:
            Upscaled PIL Image

        Raises:
            ValueError: Jika scale tidak didukung
            FileNotFoundError: Jika model file tidak ditemukan
        """
        upsampler = self._load_model(scale)

        # Ensure RGB — model hanya support 3 channel (RGBA / grayscale akan error)
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Convert PIL ke numpy array
        img_array = np.array(image)

        # Upscale
        output_array, _ = upsampler.enhance(img_array, outscale=scale)

        # Convert kembali ke PIL
        output_image = Image.fromarray(output_array)

        return output_image
