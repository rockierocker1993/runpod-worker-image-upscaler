"""
Real-ESRGAN Image Upscaler.
"""
import os
import logging
import numpy as np
from PIL import Image
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer

logger = logging.getLogger("runpod-upscaler")


class ImageUpscaler:
    """
    Real-ESRGAN image upscaler.
    Mendukung scale 2x dan 4x.
    """
    
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
                tile=0,
                tile_pad=10,
                pre_pad=0,
                half=False,
            )
            logger.info("Loaded %s model for scale %sx", cfg["name"], scale)
        
        return self._cache[scale]
    
    def upscale(self, image: Image.Image, scale: int = 4) -> Image.Image:
        """
        Upscale image dengan scale factor tertentu.
        
        Args:
            image: Input PIL Image (RGB)
            scale: Scale factor (2 atau 4)
            
        Returns:
            Upscaled PIL Image
            
        Raises:
            ValueError: Jika scale tidak didukung
            FileNotFoundError: Jika model file tidak ditemukan
        """
        upsampler = self._load_model(scale)
        
        # Convert PIL ke numpy array
        img_array = np.array(image)
        
        # Upscale
        output_array, _ = upsampler.enhance(img_array, outscale=scale)
        
        # Convert kembali ke PIL
        output_image = Image.fromarray(output_array)
        
        return output_image
