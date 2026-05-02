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
# S3 configuration (from environment variables)
# ---------------------------------------------------------------------------

S3_BUCKET = os.environ["S3_BUCKET"]
S3_REGION = os.environ.get("S3_REGION", "us-east-1")
S3_KEY_PREFIX = os.environ.get("S3_KEY_PREFIX", "upscaled/")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL")
DELETE_INPUT_AFTER_UPSCALE = os.environ.get("DELETE_INPUT_AFTER_UPSCALE", "false")
WEBHOOK_CALLBACK_URL = os.environ.get("WEBHOOK_CALLBACK_URL")
WEBHOOK_TIMEOUT_SECONDS = float(os.environ.get("WEBHOOK_TIMEOUT_SECONDS", "10"))
WEBHOOK_AUTH_TOKEN = os.environ.get("WEBHOOK_AUTH_TOKEN")
ENABLE_DATABASE = os.environ.get("ENABLE_DATABASE", "false")

_s3_config = Config(
    s3={
        "addressing_style": "path" if S3_ENDPOINT_URL else "auto",
    }
)

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


def _upload_to_s3(image: Image.Image, key_prefix: str, output_format: str = "png", output_quality: int = 95) -> tuple[str, str]:
    """Upload a PIL image to S3 and return its public URL and format.
    
    Args:
        image: PIL Image to upload
        key_prefix: S3 key prefix
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
    
    # Determine file extension and content type
    ext_map = {"jpeg": "jpg", "png": "png", "webp": "webp"}
    content_type_map = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    
    ext = ext_map.get(fmt, "png")
    content_type = content_type_map.get(fmt, "image/png")
    object_key = f"{key_prefix}{uuid.uuid4().hex}.{ext}"

    _s3_client.upload_fileobj(
        buffer,
        S3_BUCKET,
        object_key,
        ExtraArgs={"ContentType": content_type},
    )

    return _build_object_url(object_key), ext


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


def _send_webhook_callback(payload: dict) -> None:
    """Send callback payload to webhook endpoint."""
    if not WEBHOOK_CALLBACK_URL:
        return

    headers = {"Content-Type": "application/json"}
    if WEBHOOK_AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {WEBHOOK_AUTH_TOKEN}"

    started_at = time.perf_counter()

    try:
        response = requests.post(
            WEBHOOK_CALLBACK_URL,
            json=payload,
            headers=headers,
            timeout=WEBHOOK_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        logger.info(
            "Job %s webhook callback sent | status=%s | elapsed=%.3fs",
            payload.get("job_id"),
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


def _trigger_webhook_async(payload: dict) -> None:
    """Dispatch webhook callback in a daemon thread so handler can return immediately."""
    if not WEBHOOK_CALLBACK_URL:
        return

    thread = threading.Thread(target=_send_webhook_callback, args=(payload,), daemon=True)
    thread.start()


def _utc_now_iso() -> str:
    """Return current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _build_final_response(payload: dict, status: str) -> dict:
    """Attach status and webhook trigger info, then dispatch async callback when enabled."""
    response_payload = dict(payload)
    response_payload["status"] = status
    response_payload["error_message"] = response_payload.get("error") if status == "error" else None

    webhook_triggered_at = _utc_now_iso() if WEBHOOK_CALLBACK_URL else None
    response_payload["webhook_triggered_at"] = webhook_triggered_at

    if WEBHOOK_CALLBACK_URL:
        _trigger_webhook_async(response_payload)

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

    # --- Validate input ---
    image_key: str | None = job_input.get("image")
    if not image_key:
        logger.warning("Job %s rejected: missing image", runpod_job_id)
        return _build_final_response(
            {
                "job_id": runpod_job_id,
                "error": "Missing required field: image",
            },
            status="error",
        )

    scale: int = int(job_input.get("scale", 4))
    if scale not in ImageUpscaler.MODEL_CONFIGS:
        logger.warning("Job %s rejected: unsupported scale=%s", runpod_job_id, scale)
        return _build_final_response(
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
        return _build_final_response(
            {
                "job_id": runpod_job_id,
                "error": f"Unsupported output_format: {output_format}. Must be one of {valid_formats}",
            },
            status="error",
        )
    
    # Validate quality
    if not (1 <= output_quality <= 100):
        logger.warning("Job %s rejected: invalid output_quality=%s", runpod_job_id, output_quality)
        return _build_final_response(
            {
                "job_id": runpod_job_id,
                "error": f"Invalid output_quality: {output_quality}. Must be between 1-100",
            },
            status="error",
        )

    logger.info("Job %s started | scale=%s | image=%s | format=%s | quality=%s", runpod_job_id, scale, image_key, output_format, output_quality)

    # --- Download source image from S3 ---
    try:
        image, source_url = _download_image_from_s3(image_key)
        logger.info("Job %s image decoded | size=%sx%s", runpod_job_id, image.size[0], image.size[1])
    except (BotoCoreError, ClientError) as exc:
        logger.exception("Job %s S3 download failed", runpod_job_id)
        return _build_final_response(
            {
                "job_id": runpod_job_id,
                "error": f"S3 download failed: {exc}",
            },
            status="error",
        )
    except Exception as exc:
        logger.exception("Job %s image decode failed", runpod_job_id)
        return _build_final_response(
            {
                "job_id": runpod_job_id,
                "error": f"Failed to decode image from S3: {exc}",
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
        return _build_final_response(
            {
                "job_id": runpod_job_id,
                "error": f"Upscaling failed: {exc}",
            },
            status="error",
        )

    # --- Upload result to S3 ---
    try:
        s3_url, final_format = _upload_to_s3(output_image, S3_KEY_PREFIX, output_format, output_quality)
        logger.info("Job %s uploaded to S3 | url=%s | format=%s", runpod_job_id, s3_url, final_format)
    except (BotoCoreError, ClientError) as exc:
        logger.exception("Job %s S3 upload failed", runpod_job_id)
        return _build_final_response(
            {
                "job_id": runpod_job_id,
                "error": f"S3 upload failed: {exc}",
            },
            status="error",
        )

    # --- Delete input image from S3 (optional) ---
    if _to_bool(DELETE_INPUT_AFTER_UPSCALE):
        try:
            _delete_from_s3(image_key)
            logger.info("Job %s input image deleted from S3 | key=%s", runpod_job_id, image_key)
        except (BotoCoreError, ClientError) as exc:
            logger.warning("Job %s failed to delete input image from S3: %s", runpod_job_id, exc)
            # Don't fail the job if delete fails, just log warning

    processing_time = round(time.perf_counter() - start_time, 4)

    # --- Save record to database (optional) ---
    if db_enabled:
        try:
            record = save_upscaled_image(
                job_id=runpod_job_id,
                processing_time=processing_time,
                original_url=source_url,
                output_url=s3_url,
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
            return _build_final_response(
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
        "output_url": s3_url,
        "format": final_format,
        "output_format": final_format,
        "output_quality": output_quality if final_format in ["jpg", "jpeg", "webp"] else None,
        "original_size": list(image.size),
        "output_size": list(output_image.size),
        "scale": scale
    }

    return _build_final_response(response_payload, status="success")


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
