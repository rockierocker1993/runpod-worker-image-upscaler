import io
import os
import uuid
import time
import logging
import threading
from datetime import datetime, timezone
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
import runpod
import requests
from PIL import Image
from db import save_upscaled_image
from upscaler import ImageUpscaler

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("runpod-upscaler")

# ---------------------------------------------------------------------------
# Storage configuration (from environment variables)
# ---------------------------------------------------------------------------

# Input storage mode
INPUT_STORAGE_MODE = os.environ.get("INPUT_STORAGE_MODE", "s3").lower()  # s3 or volume
INPUT_VOLUME_PATH = os.environ.get("INPUT_VOLUME_PATH", "/runpod-volume/inputs/")

# S3 configuration (for S3 input mode)
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL")
DELETE_INPUT_AFTER_UPSCALE = os.environ.get("DELETE_INPUT_AFTER_UPSCALE", "false")

# Output storage mode
OUTPUT_STORAGE_MODE = os.environ.get("OUTPUT_STORAGE_MODE", "cloudflare").lower()  # cloudflare or volume
OUTPUT_VOLUME_PATH = os.environ.get("OUTPUT_VOLUME_PATH", "/runpod-volume/outputs/")

# ---------------------------------------------------------------------------
# Cloudflare Images configuration (for cloudflare output mode)
# ---------------------------------------------------------------------------

CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_IMAGES_URL = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/images/v1" if CLOUDFLARE_ACCOUNT_ID else ""

# ---------------------------------------------------------------------------
# Webhook & Database configuration
# ---------------------------------------------------------------------------

WEBHOOK_CALLBACK_URL = os.environ.get("WEBHOOK_CALLBACK_URL")
WEBHOOK_TIMEOUT_SECONDS = float(os.environ.get("WEBHOOK_TIMEOUT_SECONDS", "10"))
WEBHOOK_AUTH_TOKEN = os.environ.get("WEBHOOK_AUTH_TOKEN")
ENABLE_DATABASE = os.environ.get("ENABLE_DATABASE", "false")

_s3_config = Config(
    s3={
        "addressing_style": "path" if S3_ENDPOINT_URL else "auto",
    }
)

# Initialize S3 client only if S3 mode is used
_s3_client = None
if INPUT_STORAGE_MODE == "s3" or OUTPUT_STORAGE_MODE == "s3":
    _s3_client = boto3.client(
        "s3",
        region_name=S3_REGION,
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        config=_s3_config,
    )


def _build_object_url(object_key: str) -> str:
    """Build object URL for either AWS S3 or S3-compatible endpoints like RunPod."""
    if S3_ENDPOINT_URL:
        return f"{S3_ENDPOINT_URL.rstrip('/')}/{S3_BUCKET}/{object_key}"
    return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{object_key}"


def _upload_to_cloudflare(image: Image.Image, output_format: str = "png", output_quality: int = 95) -> tuple[str, str]:
    """Upload a PIL image to Cloudflare Images and return its public URL and format.
    
    Args:
        image: PIL Image to upload
        output_format: Output format (png, jpg, webp)
        output_quality: Quality for lossy formats (1-100)
    
    Returns:
        Tuple of (url, format)
    """
    buffer = io.BytesIO()
    
    # Normalize format
    fmt = output_format.lower()
    if fmt == "jpg":
        fmt = "jpeg"
    
    # Save with appropriate settings
    if fmt in ["jpeg", "webp"]:
        # Convert RGBA to RGB for formats that don't support transparency
        if image.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None)
            image = background
        image.save(buffer, format=fmt.upper(), quality=output_quality, optimize=True)
    else:
        # PNG or other lossless formats
        image.save(buffer, format="PNG", optimize=True)
        fmt = "png"
    
    buffer.seek(0)
    
    # Determine file extension
    ext_map = {"jpeg": "jpg", "png": "png", "webp": "webp"}
    ext = ext_map.get(fmt, "png")
    
    # Generate custom ID with timestamp path: upscale-results/YYYY/MM/DD/filename.ext
    now = datetime.now(timezone.utc)
    image_name = f"{uuid.uuid4().hex}.{ext}"
    custom_id = f"upscale-results/{now.year}/{now.month:02d}/{now.day:02d}/{image_name}"
    
    # Prepare multipart form data
    files = {
        'file': (image_name, buffer, f'image/{ext}')
    }
    data = {
        'metadata': '{"key":"upscaler"}',
        'requireSignedURLs': 'false',
        'id': custom_id
    }
    headers = {
        'Authorization': f'Bearer {CLOUDFLARE_API_TOKEN}'
    }
    
    # Upload to Cloudflare Images
    response = requests.post(
        CLOUDFLARE_IMAGES_URL,
        files=files,
        data=data,
        headers=headers,
        timeout=30
    )
    response.raise_for_status()
    
    result = response.json()
    if not result.get('success'):
        raise Exception(f"Cloudflare upload failed: {result.get('errors')}")
    
    # Get the public variant URL
    variants = result.get('result', {}).get('variants', [])
    if not variants:
        raise Exception("No image variants returned from Cloudflare")
    
    # Use the first variant (public URL)
    image_url = variants[0]
    
    return image_url, ext


def _download_image_from_s3(object_key: str) -> tuple[Image.Image, str]:
    """Download source image from configured S3 bucket using object key."""
    response = _s3_client.get_object(Bucket=S3_BUCKET, Key=object_key)
    payload = response["Body"].read()
    image = Image.open(io.BytesIO(payload)).convert("RGB")
    return image, _build_object_url(object_key)


def _delete_from_s3(object_key: str) -> None:
    """Delete object from S3 bucket."""
    _s3_client.delete_object(Bucket=S3_BUCKET, Key=object_key)
    logger.info("Deleted S3 object: %s", object_key)


def _read_image_from_volume(image_path: str) -> tuple[Image.Image, str]:
    """Read source image from network volume.
    
    Args:
        image_path: Relative path from INPUT_VOLUME_PATH or absolute path
    
    Returns:
        Tuple of (image, full_path)
    """
    # Build full path
    full_path = os.path.join(INPUT_VOLUME_PATH, image_path) if not image_path.startswith('/') else image_path
    
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Image not found: {full_path}")
    
    image = Image.open(full_path).convert("RGB")
    return image, full_path


def _save_image_to_volume(image: Image.Image, output_format: str = "png", output_quality: int = 95) -> tuple[str, str]:
    """Save image to network volume and return file path and format.
    
    Args:
        image: PIL Image to save
        output_format: Output format (png, jpg, webp)
        output_quality: Quality for lossy formats (1-100)
    
    Returns:
        Tuple of (file_path, format)
    """
    # Normalize format
    fmt = output_format.lower()
    if fmt == "jpg":
        fmt = "jpeg"
    
    # Convert RGBA to RGB for formats that don't support transparency
    if fmt in ["jpeg", "webp"]:
        if image.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None)
            image = background
    
    # Determine file extension
    ext_map = {"jpeg": "jpg", "png": "png", "webp": "webp"}
    ext = ext_map.get(fmt, "png")
    
    # Generate path with timestamp: outputs/YYYY/MM/DD/filename.ext
    now = datetime.now(timezone.utc)
    date_path = f"{now.year}/{now.month:02d}/{now.day:02d}"
    filename = f"{uuid.uuid4().hex}.{ext}"
    relative_path = os.path.join(date_path, filename)
    full_path = os.path.join(OUTPUT_VOLUME_PATH, relative_path)
    
    # Create directory if not exists
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    
    # Save image
    if fmt in ["jpeg", "webp"]:
        image.save(full_path, format=fmt.upper(), quality=output_quality, optimize=True)
    else:
        image.save(full_path, format="PNG", optimize=True)
    
    return full_path, ext


def _delete_from_volume(file_path: str) -> None:
    """Delete file from network volume."""
    try:
        os.remove(file_path)
        logger.info("Deleted volume file: %s", file_path)
    except OSError as e:
        logger.warning("Failed to delete volume file %s: %s", file_path, e)


def _send_webhook_callback(payload: dict, webhook_url: str | None = None) -> None:
    """Send callback payload to webhook endpoint."""
    effective_url = webhook_url or WEBHOOK_CALLBACK_URL
    if not effective_url:
        return

    headers = {"Content-Type": "application/json"}
    if WEBHOOK_AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {WEBHOOK_AUTH_TOKEN}"

    started_at = time.perf_counter()

    try:
        response = requests.post(
            effective_url,
            json=payload,
            headers=headers,
            timeout=WEBHOOK_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        logger.info(
            "Job %s webhook callback sent | url=%s | status=%s | elapsed=%.3fs",
            payload.get("job_id"),
            effective_url,
            response.status_code,
            time.perf_counter() - started_at,
        )
    except requests.RequestException as exc:
        logger.exception(
            "Job %s webhook callback failed after %.3fs: %s",
            payload.get("job_id"),
            time.perf_counter() - started_at,
            exc,
        )


def _trigger_webhook_async(payload: dict, webhook_url: str | None = None) -> None:
    """Dispatch webhook callback in a daemon thread so handler can return immediately."""
    effective_url = webhook_url or WEBHOOK_CALLBACK_URL
    if not effective_url:
        return

    thread = threading.Thread(target=_send_webhook_callback, args=(payload, effective_url), daemon=True)
    thread.start()


def _utc_now_iso() -> str:
    """Return current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _build_final_response(payload: dict, status: str, webhook_url: str | None = None, webhook_enabled: bool = True) -> dict:
    """Attach status and webhook trigger info, then dispatch async callback when enabled."""
    response_payload = dict(payload)
    response_payload["status"] = status
    response_payload["error_message"] = response_payload.get("error") if status == "error" else None

    effective_url = webhook_url or WEBHOOK_CALLBACK_URL
    should_trigger = webhook_enabled and bool(effective_url)

    webhook_triggered_at = _utc_now_iso() if should_trigger else None
    response_payload["webhook_triggered_at"] = webhook_triggered_at

    if should_trigger:
        _trigger_webhook_async(response_payload, webhook_url=effective_url)

    return response_payload


def _to_bool(value: object) -> bool:
    """Normalize bool-like values from env/input."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Initialize upscaler
# ---------------------------------------------------------------------------

# Initialize upscaler (singleton, lazy-loads models on first use)
_upscaler = ImageUpscaler()


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def handler(job: dict) -> dict:
    """RunPod serverless handler for image upscaling."""
    start_time = time.perf_counter()
    job_input: dict = job.get("input", {})
    runpod_job_id: str | None = job.get("id")
    db_enabled: bool = _to_bool(ENABLE_DATABASE)

    # --- Webhook config (per-request overrides env defaults) ---
    request_webhook_url: str | None = job_input.get("webhook_url") or None
    webhook_enabled: bool = _to_bool(job_input.get("webhook_enabled", True))
    logger.debug(
        "Job %s webhook config | enabled=%s | url=%s",
        runpod_job_id,
        webhook_enabled,
        request_webhook_url or "(env default)",
    )

    # Local helper: forward webhook config to every response in this job
    def _respond(payload: dict, status: str) -> dict:
        return _build_final_response(
            payload, status=status,
            webhook_url=request_webhook_url,
            webhook_enabled=webhook_enabled,
        )

    # --- Validate input ---
    image_key: str | None = job_input.get("image")
    if not image_key:
        logger.warning("Job %s rejected: missing image", runpod_job_id)
        return _respond(
            {
                "job_id": runpod_job_id,
                "error": "Missing required field: image",
            },
            status="error",
        )

    scale: int = int(job_input.get("scale", 4))
    if scale not in ImageUpscaler.MODEL_CONFIGS:
        logger.warning("Job %s rejected: unsupported scale=%s", runpod_job_id, scale)
        return _respond(
            {
                "job_id": runpod_job_id,
                "error": f"Unsupported scale: {scale}. Must be one of {list(ImageUpscaler.MODEL_CONFIGS.keys())}",
            },
            status="error",
        )

    # Output format settings
    output_format: str = job_input.get("output_format", "png").lower()
    output_quality: int = int(job_input.get("output_quality", 95))
    
    # Validate output format
    valid_formats = ["png", "jpg", "jpeg", "webp"]
    if output_format not in valid_formats:
        logger.warning("Job %s rejected: unsupported output_format=%s", runpod_job_id, output_format)
        return _respond(
            {
                "job_id": runpod_job_id,
                "error": f"Unsupported output_format: {output_format}. Must be one of {valid_formats}",
            },
            status="error",
        )
    
    # Validate quality
    if not (1 <= output_quality <= 100):
        logger.warning("Job %s rejected: invalid output_quality=%s", runpod_job_id, output_quality)
        return _respond(
            {
                "job_id": runpod_job_id,
                "error": f"Invalid output_quality: {output_quality}. Must be between 1-100",
            },
            status="error",
        )

    logger.info("Job %s started | scale=%s | image=%s | format=%s | quality=%s", runpod_job_id, scale, image_key, output_format, output_quality)

    # --- Load source image (from S3 or Volume) ---
    source_path = None
    try:
        if INPUT_STORAGE_MODE == "volume":
            image, source_path = _read_image_from_volume(image_key)
            logger.info("Job %s image loaded from volume | path=%s | size=%sx%s", 
                       runpod_job_id, source_path, image.size[0], image.size[1])
        else:  # s3
            image, source_path = _download_image_from_s3(image_key)
            logger.info("Job %s image downloaded from S3 | size=%sx%s", 
                       runpod_job_id, image.size[0], image.size[1])
    except FileNotFoundError as exc:
        logger.exception("Job %s image not found in volume", runpod_job_id)
        return _respond(
            {
                "job_id": runpod_job_id,
                "error": f"Image not found: {exc}",
            },
            status="error",
        )
    except (BotoCoreError, ClientError) as exc:
        logger.exception("Job %s S3 download failed", runpod_job_id)
        return _respond(
            {
                "job_id": runpod_job_id,
                "error": f"S3 download failed: {exc}",
            },
            status="error",
        )
    except Exception as exc:
        logger.exception("Job %s image load failed", runpod_job_id)
        return _respond(
            {
                "job_id": runpod_job_id,
                "error": f"Failed to load image: {exc}",
            },
            status="error",
        )

    # --- Upscale image ---
    try:
        upscale_start = time.perf_counter()
        output_image = _upscaler.upscale(image, scale)
        logger.info(
            "Job %s upscaled | output=%sx%s | elapsed=%.2fs",
            runpod_job_id,
            output_image.size[0],
            output_image.size[1],
            time.perf_counter() - upscale_start,
        )
    except Exception as exc:
        logger.exception("Job %s upscaling failed", runpod_job_id)
        return _respond(
            {
                "job_id": runpod_job_id,
                "error": f"Upscaling failed: {exc}",
            },
            status="error",
        )

    # --- Save result (to Cloudflare or Volume) ---
    output_url = None
    output_volume_path = None
    
    try:
        if OUTPUT_STORAGE_MODE == "volume":
            output_volume_path, final_format = _save_image_to_volume(output_image, output_format, output_quality)
            logger.info("Job %s saved to volume | path=%s | format=%s", runpod_job_id, output_volume_path, final_format)
        else:  # cloudflare
            output_url, final_format = _upload_to_cloudflare(output_image, output_format, output_quality)
            logger.info("Job %s uploaded to Cloudflare Images | url=%s | format=%s", runpod_job_id, output_url, final_format)
    except requests.RequestException as exc:
        logger.exception("Job %s Cloudflare upload failed", runpod_job_id)
        return _respond(
            {
                "job_id": runpod_job_id,
                "error": f"Cloudflare upload failed: {exc}",
            },
            status="error",
        )
    except Exception as exc:
        logger.exception("Job %s output save failed", runpod_job_id)
        return _respond(
            {
                "job_id": runpod_job_id,
                "error": f"Failed to save output: {exc}",
            },
            status="error",
        )

    # --- Delete input (optional) ---
    if _to_bool(DELETE_INPUT_AFTER_UPSCALE):
        try:
            if INPUT_STORAGE_MODE == "volume":
                _delete_from_volume(source_path)
                logger.info("Job %s input deleted from volume | path=%s", runpod_job_id, source_path)
            else:  # s3
                _delete_from_s3(image_key)
                logger.info("Job %s input deleted from S3 | key=%s", runpod_job_id, image_key)
        except Exception as exc:
            logger.warning("Job %s failed to delete input: %s", runpod_job_id, exc)
            # Don't fail the job if delete fails, just log warning

    processing_time = round(time.perf_counter() - start_time, 4)

    # --- Save record to database (optional) ---
    if db_enabled:
        try:
            record = save_upscaled_image(
                job_id=runpod_job_id,
                processing_time=processing_time,
                original_url=source_path,
                output_url=output_url or output_volume_path,
                scale=scale,
                original_size=image.size,
                output_size=output_image.size,
            )
            record_id = record.id
            logger.info(
                "Job %s DB insert success | record_id=%s | processing_time=%.4fs",
                runpod_job_id,
                record_id,
                processing_time,
            )
        except Exception as exc:
            logger.exception("Job %s database insert failed", runpod_job_id)
            return _respond(
                {
                    "job_id": runpod_job_id,
                    "error": f"Database insert failed: {exc}",
                    "database_enabled": db_enabled,
                },
                status="error",
            )
    else:
        logger.info("Job %s DB insert skipped | enable_database=false", runpod_job_id)

    logger.info("Job %s completed | total_elapsed=%.2fs", runpod_job_id, time.perf_counter() - start_time)

    response_payload = {
        "job_id": runpod_job_id,
        "processing_time": processing_time,
        "input_storage_mode": INPUT_STORAGE_MODE,
        "output_storage_mode": OUTPUT_STORAGE_MODE,
        "output_url": output_url,
        "output_volume": output_volume_path,
        "format": final_format,
        "output_format": final_format,
        "output_quality": output_quality if final_format in ["jpg", "jpeg", "webp"] else None,
        "original_size": list(image.size),
        "output_size": list(output_image.size),
        "scale": scale
    }

    return _respond(response_payload, status="success")


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
