# RunPod Worker Image Upscaler

RunPod serverless worker untuk upscaling gambar menggunakan RealESRGAN.

## Fitur
- Download gambar sumber dari S3 (atau S3-compatible endpoint).
- Upscale gambar 2x atau 4x.
- Upload hasil ke S3 sebagai PNG.
- Simpan metadata ke database (opsional, bisa enable/disable per job).
- Webhook callback async untuk status success maupun error.

## Alur Singkat
1. Worker membaca input job (`image_key`, `scale`, dan optional `properties`).
2. Worker download gambar dari bucket S3.
3. Worker menjalankan proses upscaling.
4. Worker upload hasil ke S3.
5. Worker menyimpan ke DB hanya jika database di-enable.
6. Worker mengembalikan response dan trigger webhook async (jika URL webhook dikonfigurasi).

## Requirement
- Docker dan Docker Compose.
- Bucket/object storage yang kompatibel S3.
- Model RealESRGAN tersedia di folder `models/`.

## Konfigurasi Environment
Contoh variable tersedia di file `.env-example`.

### S3
- `S3_BUCKET` (wajib)
- `S3_REGION` (default: `us-east-1`)
- `S3_KEY_PREFIX` (default: `upscaled/`)
- `S3_ENDPOINT_URL` (opsional, untuk S3-compatible storage)
- `AWS_ACCESS_KEY_ID` (wajib)
- `AWS_SECRET_ACCESS_KEY` (wajib)

### Database
- `ENABLE_DATABASE` (default: `false`)
- `DATABASE_URL` (dibutuhkan jika `ENABLE_DATABASE=true` atau job mengaktifkan DB)

### Webhook
- `WEBHOOK_CALLBACK_URL` (opsional)
- `WEBHOOK_TIMEOUT_SECONDS` (default: `10`)
- `WEBHOOK_AUTH_TOKEN` (opsional; dikirim sebagai Bearer token)

### Model
- `MODEL_2X_PATH` (default: `/models/RealESRGAN_x2plus.pth`)
- `MODEL_4X_PATH` (default: `/models/RealESRGAN_x4plus.pth`)

## Menjalankan Worker (Docker Compose)
1. Copy `.env-example` ke `.env`, lalu isi nilainya.
2. Jalankan:

```bash
docker compose up --build
```

## Format Input Job
Minimal input:

```json
{
  "input": {
    "image_key": "input/sample.png",
    "scale": 4
  }
}
```

Enable DB per job via `properties`:

```json
{
  "input": {
    "image_key": "input/sample.png",
    "scale": 4,
    "properties": {
      "enable_database": true
    }
  }
}
```

Nilai boolean yang diterima untuk `enable_database`:
- `true`, `1`, `yes`, `on` => dianggap aktif.
- selain nilai di atas => dianggap nonaktif.

Prioritas konfigurasi database:
1. `input.properties.enable_database` (per job)
2. `ENABLE_DATABASE` (global env)
3. default internal `false`

## API Contract

### Input
- Root object: `job`
- `job.id` (string | null): id job dari RunPod.
- `job.input` (object): payload utama.
- `job.input.image_key` (string, wajib): object key sumber di bucket.
- `job.input.scale` (integer, opsional, default `4`): nilai valid hanya `2` atau `4`.
- `job.input.properties` (object, opsional): properti tambahan.
- `job.input.properties.enable_database` (bool-like, opsional): override DB mode per job.

### Response Success
- `id` (integer | null): id record DB; `null` jika DB disabled.
- `job_id` (string | null)
- `processing_time` (float)
- `input_key` (string)
- `input_url` (string)
- `image_url` (string)
- `format` (string, selalu `png`)
- `original_size` (array integer, panjang 2)
- `output_size` (array integer, panjang 2)
- `scale` (integer)
- `database_enabled` (boolean)
- `status` (string, selalu `success`)
- `error_message` (null)
- `webhook_triggered_at` (string ISO-8601 UTC | null)

### Response Error
- `job_id` (string | null)
- `error` (string)
- `error_message` (string, mirror dari field `error`)
- `database_enabled` (boolean, muncul pada error terkait DB)
- `status` (string, selalu `error`)
- `webhook_triggered_at` (string ISO-8601 UTC | null)

### Webhook Behavior
- Webhook dikirim jika `WEBHOOK_CALLBACK_URL` terisi.
- Webhook dipicu pada semua hasil (`success` dan `error`).
- Payload webhook = response final handler (tanpa transformasi).
- Dispatch webhook asynchronous (handler tidak menunggu callback selesai).

## Response Output
Response selalu mengandung:
- `status`: `success` atau `error`
- `error_message`: pesan error eksplisit (`null` saat sukses)
- `webhook_triggered_at`: waktu trigger webhook (UTC ISO-8601), atau `null` jika webhook tidak aktif

Contoh response sukses:

```json
{
  "id": 123,
  "job_id": "runpod-job-id",
  "processing_time": 1.2345,
  "input_key": "input/sample.png",
  "input_url": "https://...",
  "image_url": "https://...",
  "format": "png",
  "original_size": [512, 512],
  "output_size": [2048, 2048],
  "scale": 4,
  "database_enabled": true,
  "status": "success",
  "error_message": null,
  "webhook_triggered_at": "2026-05-01T12:34:56.123456+00:00"
}
```

Contoh response error:

```json
{
  "job_id": "runpod-job-id",
  "error": "S3 download failed: ...",
  "error_message": "S3 download failed: ...",
  "status": "error",
  "webhook_triggered_at": "2026-05-01T12:34:56.123456+00:00"
}
```

## Webhook Callback
- Callback dipanggil secara asynchronous.
- Callback dipicu untuk semua status (`success` dan `error`).
- Payload webhook adalah response final yang sama dengan output handler.

## Catatan
- Jika `database_enabled=false`, field `id` akan `null` karena tidak ada insert DB.
- Pastikan model `.pth` tersedia dan path sesuai konfigurasi.
