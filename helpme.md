# HELPME - Quick Troubleshooting

Dokumen ini untuk cek cepat ketika worker tidak berjalan sesuai harapan.

## 1) Job gagal karena input tidak valid
Gejala:
- Response berisi `Missing required field: image_key`
- Response berisi `Unsupported scale`

Cek:
- Pastikan `input.image_key` ada.
- Pastikan `input.scale` hanya `2` atau `4`.

## 2) Gagal download/upload S3
Gejala:
- `S3 download failed: ...`
- `S3 upload failed: ...`

Cek:
- Nilai `S3_BUCKET`, `S3_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.
- Jika pakai storage S3-compatible, pastikan `S3_ENDPOINT_URL` benar.
- Pastikan object key pada `image_key` benar-benar ada.
- Cek permission bucket (read untuk input, write untuk output).

## 3) Upscaling gagal
Gejala:
- `Upscaling failed: ...`

Cek:
- File model ada di folder `models/`.
- Path model sesuai (`MODEL_2X_PATH`, `MODEL_4X_PATH`).
- Volume mount models benar saat pakai Docker Compose.

## 4) Database tidak tersimpan
Gejala:
- Response sukses tetapi `id` bernilai `null`.

Penjelasan:
- DB mode sedang disable.

Cara enable DB:
- Global via env: set `ENABLE_DATABASE=true`.
- Per job: set `input.properties.enable_database=true`.

Jika sudah enable tetapi tetap gagal:
- Cek `DATABASE_URL`.
- Cek konektivitas ke PostgreSQL.
- Cek log error `Database insert failed`.

## 5) Webhook tidak terpanggil
Gejala:
- `webhook_triggered_at` bernilai `null`.

Cek:
- Set `WEBHOOK_CALLBACK_URL`.
- Pastikan endpoint dapat diakses dari container worker.

Jika `webhook_triggered_at` ada tetapi endpoint tidak menerima data:
- Cek endpoint timeout (`WEBHOOK_TIMEOUT_SECONDS`).
- Cek token auth (`WEBHOOK_AUTH_TOKEN`) jika endpoint butuh Bearer token.
- Cek log error `webhook callback failed`.

## 6) Webhook dipicu kapan?
- Webhook dipicu untuk semua status: `success` dan `error`.
- Mekanisme callback async (tidak menahan response handler).
- Payload webhook sama persis dengan response final handler.

## 7) Quick checklist sebelum deploy
- `.env` sudah terisi lengkap.
- Model `.pth` sudah tersedia.
- S3 credentials valid.
- `ENABLE_DATABASE` sesuai kebutuhan.
- `WEBHOOK_CALLBACK_URL` sudah benar (jika dipakai).
- Jalankan `docker compose up --build` tanpa error.
