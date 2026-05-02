# RunPod Worker Image Upscaler

RunPod serverless worker untuk upscaling gambar menggunakan Real-ESRGAN dengan dukungan GPU.

## 📋 Fitur

- ✅ Download gambar dari S3 atau S3-compatible storage (MinIO, R2, etc)
- ✅ Upscale gambar 2x atau 4x menggunakan Real-ESRGAN
- ✅ Multi-format output: PNG (lossless), JPG, WebP dengan quality control
- ✅ Auto-delete input image dari S3 setelah upscaling (opsional)
- ✅ Simpan metadata ke database PostgreSQL (opsional, per-job atau global)
- ✅ Webhook callback async untuk notifikasi status (success/error)
- ✅ Model bundling di Docker image
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
- **Network**: Akses ke S3 endpoint

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
│              2. Download from S3 Storage                     │
│             _download_image_from_s3(image)                   │
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
│              4. Upload Result to S3                          │
│         _upload_to_s3(output_image) → URL                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│      5. Delete Input from S3 (Optional)                      │
│   if DELETE_INPUT_AFTER_UPSCALE: delete input image          │
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

4. **Test via API**:
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

## ⚙️ Configuration

### Environment Variables

Buat file `.env` dari `.env-example`:

#### S3 Storage (Required)
```env
S3_BUCKET=your-bucket-name
S3_REGION=us-east-1
S3_KEY_PREFIX=upscaled/
S3_ENDPOINT_URL=https://your-s3-endpoint.com  # Optional, untuk non-AWS S3
DELETE_INPUT_AFTER_UPSCALE=false              # Delete input image after upscaling
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

**Note**: `DELETE_INPUT_AFTER_UPSCALE` akan menghapus input image dari S3 setelah upscaling berhasil. Set `true` untuk auto-delete.

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
    "output_quality": 90
  }
}
```

#### Input Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `input.image` | string | Yes | - | S3 object key untuk source image |
| `input.scale` | integer | No | 4 | Upscale factor (2 atau 4) |
| `input.output_format` | string | No | `png` | Output format: `png`, `jpg`, `jpeg`, `webp` |
| `input.output_quality` | integer | No | 95 | Quality untuk lossy formats (1-100) |

**Notes**: 
- `output_quality` hanya berlaku untuk `jpg` dan `webp` (lossy formats)
- PNG selalu lossless (quality diabaikan)
- Database control via `ENABLE_DATABASE` environment variable

### Output Response Format

#### Success Response
```json
{
  "status": "success",
  "job_id": "job-12345",
  "id": 42,
  "processing_time": 2.3456,
  "input": "input/sample.png",
  "input_url": "https://bucket.s3.region.amazonaws.com/input/sample.png",
  "image_url": "https://bucket.s3.region.amazonaws.com/upscaled/abc123.jpg",
  "format": "jpg",
  "output_format": "jpg",
  "output_quality": 90,
  "original_size": [1024, 768],
  "output_size": [4096, 3072],
  "scale": 4,
  "database_enabled": true,
  "webhook_triggered_at": "2026-05-02T10:30:45.123456+00:00",
  "error_message": null
}
```

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

Jika `WEBHOOK_CALLBACK_URL` dikonfigurasi, worker akan send POST request async:

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
- **output_url**: URL hasil upscale di S3
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
- RunPod handler setup
- S3 operations (download/upload)
- Webhook callbacks
- Database integration
- Error handling & logging
- Response formatting

**Key Functions**:
- `handler(job)` - Main RunPod handler
- `_download_image_from_s3()` - Download from S3
- `_upload_to_s3()` - Upload to S3
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
