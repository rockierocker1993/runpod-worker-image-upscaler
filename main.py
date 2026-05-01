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
import numpy as np
import requests
from PIL import Image
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer
from db import save_upscaled_image

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


def _upload_to_s3(image: Image.Image, key_prefix: str) -> str:
    """Upload a PIL image as PNG to S3 and return its public URL."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    object_key = f"{key_prefix}{uuid.uuid4().hex}.png"

    _s3_client.upload_fileobj(
        buffer,
        S3_BUCKET,
        object_key,
        ExtraArgs={"ContentType": "image/png"},
    )

    return _build_object_url(object_key)


def _download_image_from_s3(object_key: str) -> tuple[Image.Image, str]:
    """Download source image from configured S3 bucket using object key."""
    response = _s3_client.get_object(Bucket=S3_BUCKET, Key=object_key)
    payload = response["Body"].read()
    image = Image.open(io.BytesIO(payload)).convert("RGB")
    return image, _build_object_url(object_key)


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
# Model configuration
# ---------------------------------------------------------------------------

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

_upsampler_cache: dict = {}


def _get_upsampler(scale: int) -> RealESRGANer:
    """Return a cached RealESRGANer instance for the requested scale."""
    if scale not in MODEL_CONFIGS:
        raise ValueError(f"Unsupported scale factor: {scale}. Supported: {list(MODEL_CONFIGS.keys())}")

    if scale not in _upsampler_cache:
        cfg = MODEL_CONFIGS[scale]
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

        _upsampler_cache[scale] = RealESRGANer(
            scale=scale,
            model_path=cfg["path"],
            model=model,
            tile=0,
            tile_pad=10,
            pre_pad=0,
            half=False,
        )
        logger.info("Loaded model for scale %sx", scale)

    return _upsampler_cache[scale]


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def handler(job: dict) -> dict:
    """RunPod serverless handler for image upscaling."""
    start_time = time.perf_counter()
    job_input: dict = job.get("input", {})
    runpod_job_id: str | None = job.get("id")
    job_properties: dict = job_input.get("properties", {})
    db_enabled: bool = _to_bool(job_properties.get("enable_database", ENABLE_DATABASE))

    # --- Validate input ---
    image_key: str | None = job_input.get("image_key")
    if not image_key:
        logger.warning("Job %s rejected: missing image_key", runpod_job_id)
        return _build_final_response(
            {
                "job_id": runpod_job_id,
                "error": "Missing required field: image_key",
            },
            status="error",
        )

    scale: int = int(job_input.get("scale", 4))
    if scale not in MODEL_CONFIGS:
        logger.warning("Job %s rejected: unsupported scale=%s", runpod_job_id, scale)
        return _build_final_response(
            {
                "job_id": runpod_job_id,
                "error": f"Unsupported scale: {scale}. Must be one of {list(MODEL_CONFIGS.keys())}",
            },
            status="error",
        )

    logger.info("Job %s started | scale=%s | image_key=%s", runpod_job_id, scale, image_key)

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

    # --- Upscale ---
    try:
        upscale_start = time.perf_counter()
        upsampler = _get_upsampler(scale)
        img_array = np.array(image)
        output_array, _ = upsampler.enhance(img_array, outscale=scale)
        output_image = Image.fromarray(output_array)
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
        s3_url = _upload_to_s3(output_image, S3_KEY_PREFIX)
        logger.info("Job %s uploaded to S3 | url=%s", runpod_job_id, s3_url)
    except (BotoCoreError, ClientError) as exc:
        logger.exception("Job %s S3 upload failed", runpod_job_id)
        return _build_final_response(
            {
                "job_id": runpod_job_id,
                "error": f"S3 upload failed: {exc}",
            },
            status="error",
        )

    processing_time = round(time.perf_counter() - start_time, 4)
    record_id: int | None = None

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
        "id": record_id,
        "job_id": runpod_job_id,
        "processing_time": processing_time,
        "input_key": image_key,
        "input_url": source_url,
        "image_url": s3_url,
        "format": "png",
        "original_size": list(image.size),
        "output_size": list(output_image.size),
        "scale": scale,
        "database_enabled": db_enabled,
    }

    return _build_final_response(response_payload, status="success")


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
