# RunPod Worker Image Upscaler

RunPod serverless worker untuk upscaling gambar menggunakan Real-ESRGAN dengan dukungan GPU.

## 📋 Fitur

- ✅ **Flexible Input Storage**: S3 atau RunPod Network Volume
- ✅ **Flexible Output Storage**: Cloudflare Images (CDN) atau Network Volume
- ✅ Upscale gambar 2x atau 4x menggunakan Real-ESRGAN
- ✅ Multi-format output: PNG (lossless), JPG, WebP dengan quality control
- ✅ Auto-delete input image setelah upscaling (opsional)
- ✅ Simpan metadata ke database PostgreSQL (opsional)
- ✅ Webhook callback async untuk notifikasi status (success/error)
- ✅ Model bundling di Docker image atau dari Network Volume
- ✅ GPU acceleration (CUDA 11.8)

## 🖥️ System Requirements

### Hardware
- **GPU**: NVIDIA GPU dengan CUDA support (minimal 4GB VRAM)
- **RAM**: Minimal 8GB (16GB recommended)
- **Storage**: ~10GB untuk Docker image + models
- **CPU**: Multi-core processor (4+ cores recommended)

### Software
- **Docker**: 20.10 atau lebih baru
- **Docker Compose**: 2.0 atau lebih baru
- **NVIDIA Container Toolkit**: Untuk GPU support di Docker
- **CUDA**: 11.8 (sudah include di base image)

### Cloud (RunPod)
- **GPU Instance**: RTX 3080/3090, A4000, A5000, atau lebih tinggi
- **Disk Space**: Minimal 10GB
- **Network**: Akses ke S3 endpoint (input) dan Cloudflare API (output)

## 📦 Dependencies

### Python Packages
```
runpod              # RunPod serverless SDK
Pillow              # Image processing
numpy<2.0.0         # Array operations
basicsr             # ESRGAN architecture
realesrgan          # Real-ESRGAN upscaler
boto3               # AWS S3 client
requests            # HTTP requests
sqlalchemy          # Database ORM
psycopg2-binary     # PostgreSQL driver
```

### CUDA Libraries
- PyTorch 2.1.2 (CUDA 11.8)
- torchvision 0.16.2

### System Libraries
- libgl1 (OpenGL)
- libglib2.0-0 (GLib)

## 📁 Project Structure

```
runpod-worker-image-upscaler/
├── main.py                  # RunPod handler & pipeline flow
├── upscaler.py             # Real-ESRGAN upscaling logic
├── db/                     # Database module
│   ├── __init__.py        # Exports
│   ├── database.py        # Database connection
│   ├── models.py          # SQLAlchemy models
│   ├── service.py         # Database operations
│   └── migrations/        # SQL migrations
│       └── init.sql       # Initial schema
├── models/                # Pre-trained models (bundled)
│   ├── RealESRGAN_x2plus.pth
│   └── RealESRGAN_x4plus.pth
├── Dockerfile             # Container definition
├── docker-compose.yml     # Local development setup
├── requirements.txt       # Python dependencies
├── .env-example          # Environment template
├── .gitignore            # Git ignore rules
└── README.md             # Documentation
```

## 🔄 Processing Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     RunPod Job Input                         │
│         { image, scale, output_format, quality }             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   1. Validate Input                          │
│     Check image, scale, output_format, output_quality        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│         2. Load Image (S3 or Network Volume)                 │
│   • S3 mode: _download_image_from_s3()                       │
│   • Volume mode: _read_image_from_volume()                   │
│                 → PIL Image (RGB)                            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              3. Upscale Image (GPU)                          │
│           ImageUpscaler.upscale(image, scale)                │
│                                                              │
│   • Load model (cached)                                      │
│   • Convert PIL → numpy array                                │
│   • RealESRGANer.enhance() → GPU processing                  │
│   • Convert numpy → PIL Image                                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│       4. Save Result (Cloudflare or Network Volume)          │
│   • Cloudflare mode: _upload_to_cloudflare() → URL           │
│   • Volume mode: _save_image_to_volume() → Path              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│      5. Delete Input (Optional)                              │
│   if DELETE_INPUT_AFTER_UPSCALE: delete from S3/volume       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│         6. Save to Database (Optional)                       │
│    if db_enabled: save_upscaled_image(metadata)              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│         7. Send Webhook Callback (Async)                     │
│      POST to WEBHOOK_CALLBACK_URL with result                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  Return Response                             │
│    { job_id, image_url, processing_time, ... }               │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Prerequisites

Pastikan Anda sudah install:
- Docker & Docker Compose
- NVIDIA Container Toolkit (untuk GPU support)
- Git

### 2. Clone & Setup

```bash
# Clone repository
git clone <repository-url>
cd runpod-worker-image-upscaler

# Download model files (jika belum ada)
# Letakkan file model di folder models/:
# - RealESRGAN_x2plus.pth
# - RealESRGAN_x4plus.pth

# Copy environment template
cp .env-example .env

# Edit .env dengan konfigurasi Anda
nano .env
```

### 3. Build Docker Image

```bash
docker compose build
```

Build time: ~5-10 menit (tergantung koneksi internet)

### 4. Run Locally

```bash
docker build -t your-username/runpod-upscaler:latest .
```

### 5. Deploy to RunPod

1. **Push image to Docker Hub**:
   ```bash
   docker push your-username/runpod-upscaler:latest
   ```

2. **Create RunPod Serverless Template**:
   - Go to RunPod → Serverless → Templates
   - Container Image: `your-username/runpod-upscaler:latest`
   - Container Disk: 10GB minimum
   - Add environment variables from `.env`

3. **Deploy Endpoint**:
   - Select GPU type (recommend: RTX 3090 or A5000)
   - Set worker count & max workers
   - Deploy endpoint

4. **(Optional) Setup Network Volume**:
   - Create Network Volume di RunPod (if using volume storage mode)
   - Attach volume ke serverless endpoint
   - Mount path: `/runpod-volume`
   - Upload models & input images ke volume

5. **Test via API**:
   ```bash
   curl -X POST https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/run \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "input": {
         "image": "folder/image.jpg",
         "scale": 4,
         "output_format": "jpg",
         "output_quality": 90
       }
     }'
   ```

## 📦 Network Volume Setup (Optional)

Network Volume memberikan persistent storage untuk models dan images.

### Upload Models ke Network Volume

```bash
# SSH ke RunPod Pod atau gunakan file manager
mkdir -p /runpod-volume/models
cd /runpod-volume/models

# Download models
wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth
wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth
```

### Upload Input Images

```bash
# Create inputs directory
mkdir -p /runpod-volume/inputs

# Upload images (via SCP, rsync, or RunPod file manager)
scp -r /local/images/* user@pod:/runpod-volume/inputs/
```

### Environment Variables untuk Volume Mode

```env
# Use models from network volume
MODEL_2X_PATH=/runpod-volume/models/RealESRGAN_x2plus.pth
MODEL_4X_PATH=/runpod-volume/models/RealESRGAN_x4plus.pth

# Use volume for input/output
INPUT_STORAGE_MODE=volume
OUTPUT_STORAGE_MODE=volume
```

**Benefits**:
- ✅ Smaller Docker image (~2GB vs ~10GB)
- ✅ Faster cold starts
- ✅ Update models without rebuilding image
- ✅ Shared storage across workers
   ```

## ⚙️ Configuration

### Environment Variables

Buat file `.env` dari `.env-example`:

#### Storage Configuration
```env
# Input Storage Mode
INPUT_STORAGE_MODE=s3                  # s3 or volume
INPUT_VOLUME_PATH=/runpod-volume/inputs/

# Output Storage Mode
OUTPUT_STORAGE_MODE=cloudflare         # cloudflare or volume
OUTPUT_VOLUME_PATH=/runpod-volume/outputs/

# Auto-delete input after processing
DELETE_INPUT_AFTER_UPSCALE=false
```

**Storage Modes**:

| Mode | Input | Output | Use Case |
|------|-------|--------|----------|
| **S3 + Cloudflare** | S3 bucket | Cloudflare Images CDN | External storage + global CDN delivery |
| **Volume + Volume** | Network Volume | Network Volume | All-in-one RunPod storage (fastest) |
| **Volume + Cloudflare** | Network Volume | Cloudflare Images CDN | Bulk processing + CDN delivery |
| **S3 + Volume** | S3 bucket | Network Volume | External input + local archive |

#### S3 Configuration (when INPUT_STORAGE_MODE=s3)
```env
S3_BUCKET=your-bucket-name
S3_REGION=us-east-1
S3_ENDPOINT_URL=https://your-s3-endpoint.com  # Optional, untuk non-AWS S3
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

#### Cloudflare Images (when OUTPUT_STORAGE_MODE=cloudflare)
```env
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_API_TOKEN=your-api-token
```

**Output Paths**:
- **Cloudflare**: `upscale-results/YYYY/MM/DD/{uuid}.{ext}`
- **Volume**: `/runpod-volume/outputs/YYYY/MM/DD/{uuid}.{ext}`

#### Database (Optional)
```env
ENABLE_DATABASE=false                          # Global setting
DATABASE_URL=postgresql://user:pass@host:5432/dbname
```

#### Webhook (Optional)
```env
WEBHOOK_CALLBACK_URL=https://your-api.com/webhook
WEBHOOK_TIMEOUT_SECONDS=10
WEBHOOK_AUTH_TOKEN=your-secret-token          # Sent as Bearer token
```

#### Model Paths (Optional)
```env
MODEL_2X_PATH=/models/RealESRGAN_x2plus.pth
MODEL_4X_PATH=/models/RealESRGAN_x4plus.pth
```

#### Logging (Optional)
```env
LOG_LEVEL=INFO                                 # DEBUG, INFO, WARNING, ERROR
```

## 📡 API Reference

### Input Job Format

#### Minimal Input
```json
{
  "input": {
    "image": "input/sample.png",
    "scale": 4
  }
}
```

#### Full Input
```json
{
  "id": "job-12345",
  "input": {
    "image": "folder/image.jpg",
    "scale": 4,
    "output_format": "jpg",
    "output_quality": 90,
    "webhook_enabled": true,
    "webhook_url": "https://your-app.com/webhook/callback"
  }
}
```

#### Input Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `input.image` | string | Yes | - | Image path/key (S3 key or volume path) |
| `input.scale` | integer | No | 4 | Upscale factor (2 atau 4) |
| `input.output_format` | string | No | `png` | Output format: `png`, `jpg`, `jpeg`, `webp` |
| `input.output_quality` | integer | No | 95 | Quality untuk lossy formats (1-100) || `input.webhook_enabled` | boolean | No | `true` | Aktifkan/nonaktifkan webhook untuk job ini |
| `input.webhook_url` | string | No | - | Override `WEBHOOK_CALLBACK_URL` untuk job ini |
**Notes**: 
- `input.image` format tergantung storage mode:
  - S3 mode: `folder/image.jpg` (S3 object key)
  - Volume mode: `batch/image.jpg` (relative path dari INPUT_VOLUME_PATH)
- `output_quality` hanya berlaku untuk `jpg` dan `webp` (lossy formats)
- PNG selalu lossless (quality diabaikan)

### Output Response Format

#### Success Response (Cloudflare Output)
```json
{
  "status": "success",
  "job_id": "job-12345",
  "processing_time": 2.3456,
  "input_storage_mode": "s3",
  "output_storage_mode": "cloudflare",
  "output_url": "https://imagedelivery.net/account-hash/image-id/public",
  "output_volume": null,
  "format": "jpg",
  "output_format": "jpg",
  "output_quality": 90,
  "original_size": [1024, 768],
  "output_size": [4096, 3072],
  "scale": 4,
  "webhook_triggered_at": "2026-05-02T10:30:45.123456+00:00",
  "error_message": null
}
```

#### Success Response (Volume Output)
```json
{
  "status": "success",
  "job_id": "job-12345",
  "processing_time": 2.3456,
  "input_storage_mode": "volume",
  "output_storage_mode": "volume",
  "output_url": null,
  "output_volume": "/runpod-volume/outputs/2026/05/02/abc123def456.jpg",
  "format": "jpg",
  "output_format": "jpg",
  "output_quality": 90,
  "original_size": [1024, 768],
  "output_size": [4096, 3072],
  "scale": 4,
  "webhook_triggered_at": "2026-05-02T10:30:45.123456+00:00",
  "error_message": null
}
```

**Response Fields**:
- `input_storage_mode`: Storage mode used for input (`s3` or `volume`)
- `output_storage_mode`: Storage mode used for output (`cloudflare` or `volume`)
- `output_url`: Public URL (only when `output_storage_mode=cloudflare`)
- `output_volume`: File path in network volume (only when `output_storage_mode=volume`)

#### Error Response
```json
{
  "status": "error",
  "job_id": "job-12345",
  "error": "Unsupported scale: 8. Must be one of [2, 4]",
  "error_message": "Unsupported scale: 8. Must be one of [2, 4]",
  "webhook_triggered_at": "2026-05-02T10:30:45.123456+00:00"
}
```

### Webhook Callback

Webhook dikirim secara async (non-blocking) setelah job selesai. URL dan enable/disable bisa dikonfigurasi via env **atau** di-override per-request:

**Priority**:
1. Jika `webhook_enabled: false` di request → webhook tidak dikirim (env URL diabaikan)
2. Jika `webhook_url` diisi di request → URL tersebut digunakan
3. Jika tidak → fallback ke env `WEBHOOK_CALLBACK_URL`

**Headers:**
```
Content-Type: application/json
Authorization: Bearer <WEBHOOK_AUTH_TOKEN>  # if configured
```

**Payload:** Same as output response (success atau error)

## 🗄️ Database Schema

Table: `upscaled_images`

```sql
CREATE TABLE upscaled_images (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(255),
    processing_time DECIMAL(10, 4),
    original_url TEXT,
    output_url TEXT NOT NULL,
    scale INTEGER NOT NULL,
    original_width INTEGER,
    original_height INTEGER,
    output_width INTEGER,
    output_height INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Fields
- **id**: Auto-increment primary key
- **job_id**: RunPod job ID
- **processing_time**: Waktu processing dalam detik
- **original_url**: URL source image di S3
- **output_url**: URL hasil upscale di Cloudflare Images
- **scale**: Upscale factor (2 atau 4)
- **original_width/height**: Dimensi original image
- **output_width/height**: Dimensi output image
- **created_at**: Timestamp record dibuat

### Migration

Run migration SQL:
```bash
docker compose exec app psql $DATABASE_URL -f db/migrations/init.sql
```

## 🏗️ Code Architecture

### main.py - Pipeline Flow
**Responsibility**: Orchestration & integration
- S3 operations (download input images)
- Cloudflare Images upload (output images)
- Webhook callbacks
- Database integration
- Error handling & logging
- Response formatting

**Key Functions**:
- `handler(job)` - Main RunPod handler
- `_download_image_from_s3()` - Download from S3
- `_upload_to_cloudflare()` - Upload to Cloudflare Images
- `_send_webhook_callback()` - Send webhook
- `_build_final_response()` - Format response

### upscaler.py - Core Logic
**Responsibility**: Image upscaling dengan Real-ESRGAN
- Model loading & caching
- Image upscaling logic
- GPU processing

**Class**: `ImageUpscaler`
- `upscale(image, scale)` - Main upscaling method
- `_load_model(scale)` - Load & cache model
- `MODEL_CONFIGS` - Model configuration

**Keuntungan Separation**:
- Logic upscaler bisa digunakan standalone
- Mudah untuk testing
- Bisa ditambah logic lain (background removal, colorization, etc)
- Clear separation of concerns

## 🚢 Deploy to RunPod

### 1. Build & Push Docker Image

```bash
# Build image
docker build -t your-username/runpod-upscaler:latest .

# Push to Docker Hub
docker push your-username/runpod-upscaler:latest
```

### 2. Setup RunPod Serverless

1. Login ke [RunPod Console](https://runpod.io/)
2. Go to **Serverless** → **Create Template**
3. Configure template:
   - **Container Image**: `your-username/runpod-upscaler:latest`
   - **Container Disk**: 10 GB minimum
   - **Environment Variables**: Copy dari `.env`

### 3. Create Endpoint

1. Go to **Serverless** → **Endpoints**
2. Click **New Endpoint**
3. Select template yang sudah dibuat
4. Configure:
   - **GPU Type**: RTX 3080 atau lebih tinggi
   - **Workers**: Min/Max workers sesuai kebutuhan
   - **Idle Timeout**: 30 seconds (recommended)

### 4. Test Endpoint

```bash
curl -X POST https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/runsync \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "image": "input/test.png",
      "scale": 4,
      "output_format": "jpg",
      "output_quality": 90
    }
  }'
```

## 📊 Performance Metrics

### Processing Time (4x Upscale)
| Resolution | GPU | Time | VRAM Usage |
|------------|-----|------|------------|
| 512x512 → 2048x2048 | RTX 3080 | ~1.5s | ~2GB |
| 1024x1024 → 4096x4096 | RTX 3080 | ~3.5s | ~4GB |
| 2048x2048 → 8192x8192 | RTX 3080 | ~12s | ~8GB |

### Model Size
- **RealESRGAN_x2plus.pth**: ~64 MB
- **RealESRGAN_x4plus.pth**: ~64 MB

### Docker Image Size
- **Base size**: ~8 GB (includes CUDA, PyTorch)
- **With models**: ~8.2 GB

### Output Format Comparison

| Format | Quality | File Size (relative) | Use Case | Transparency |
|--------|---------|---------------------|----------|--------------|
| PNG | Lossless | 100% (largest) | Graphics, transparency needed | ✅ Yes |
| JPG | Lossy | 15-30% | Photos, web images | ❌ No |
| WebP | Lossy/Lossless | 20-40% | Modern web, best compression | ✅ Yes |

**Recommendations**:
- **PNG**: Untuk gambar dengan transparency atau yang memerlukan kualitas perfect
- **JPG (quality 85-95)**: Untuk foto/gambar biasa, hemat storage 70-85%
- **WebP (quality 80-90)**: Best balance antara quality dan file size

**Example File Sizes** (4096x4096 upscaled image):
- PNG: ~45 MB
- JPG (quality 95): ~8 MB (82% smaller)
- JPG (quality 85): ~5 MB (89% smaller)
- WebP (quality 90): ~6 MB (87% smaller)

## 🔧 Troubleshooting

### Model file not found

**Error**: `Model file not found: /models/RealESRGAN_x4plus.pth`

**Solution**:
1. Pastikan file model ada di folder `models/`
2. Rebuild Docker image: `docker compose build`
3. Check Dockerfile: `COPY models/ /models/` ada

### Torchvision warning

**Warning**: `The torchvision.transforms.functional_tensor module is deprecated...`

**Status**: ⚠️ Warning only (not critical)

**Explanation**:
- Ini adalah deprecation warning dari dependency (basicsr/realesrgan)
- Tidak mempengaruhi functionality
- Will be fixed when dependencies update ke torchvision 0.17+
- Safe to ignore untuk sekarang

### Out of memory (CUDA)

**Error**: `CUDA out of memory`

**Solution**:
- Gunakan GPU dengan VRAM lebih besar
- Reduce batch size (jika batch processing)
- Process image yang lebih kecil

### S3 download failed

**Error**: `S3 download failed: NoSuchKey`

**Solution**:
- Verify field `image` benar (S3 object key)
- Check S3 credentials & bucket permissions
- Verify `S3_BUCKET` dan `S3_ENDPOINT_URL` configuration

### Cloudflare upload failed

**Error**: `Cloudflare upload failed: 403 Forbidden`

**Solution**:
- Verify `CLOUDFLARE_API_TOKEN` valid dan belum expired
- Check `CLOUDFLARE_ACCOUNT_ID` benar
- Verify API token memiliki permission "Cloudflare Images: Edit"
- Check Cloudflare Images quota (free tier: 100k images)

**Error**: `No image variants returned from Cloudflare`

**Solution**:
- Check Cloudflare Images account setup
- Verify variant "public" exists di account settings
- Review Cloudflare Images documentation

### Database connection failed

**Error**: `Database insert failed: connection refused`

**Solution**:
- Check `DATABASE_URL` format correct
- Verify database server running
- Check network connectivity
- Run migrations: `db/migrations/init.sql`

### Webhook timeout

**Error**: `Job xxx webhook callback failed after 10s`

**Solution**:
- Increase `WEBHOOK_TIMEOUT_SECONDS`
- Check webhook endpoint availability
- Verify `WEBHOOK_CALLBACK_URL` correct

## 📝 Development

### Building & Testing

```bash
# Build image
docker build -t runpod-upscaler:dev .

# Test build (will warn and exit - no local test job)
docker run --rm --env-file .env runpod-upscaler:dev

# Rebuild after code changes
docker build -t runpod-upscaler:dev . --no-cache
```

### Adding New Processing Logic

Example: Background removal

1. **Create new file**: `background_remover.py`
```python
from PIL import Image

class BackgroundRemover:
    def remove(self, image: Image.Image) -> Image.Image:
        # Your logic here
        return processed_image
```

2. **Update main.py**:
```python
from background_remover import BackgroundRemover

_bg_remover = BackgroundRemover()

# In handler:
if job_input.get("process_type") == "remove_bg":
    output_image = _bg_remover.remove(image)
else:
    output_image = _upscaler.upscale(image, scale)
```

3. **Rebuild**: `docker compose build`

## 📚 Resources

- [Real-ESRGAN GitHub](https://github.com/xinntao/Real-ESRGAN)
- [List of Real-ESRGAN Model](https://github.com/xinntao/Real-ESRGAN/blob/master/docs/model_zoo.md)
- [RunPod Documentation](https://docs.runpod.io/)
- [BasicSR Documentation](https://github.com/XPixelGroup/BasicSR)
- [PyTorch CUDA Support](https://pytorch.org/get-started/locally/)

## 📄 License

[Your License Here]

## 🤝 Contributing

Contributions welcome! Please:
1. Fork repository
2. Create feature branch
3. Commit changes
4. Push to branch
5. Create Pull Request

## 💬 Support

For issues or questions:
- Create GitHub issue
- Check existing documentation
- Review troubleshooting section
