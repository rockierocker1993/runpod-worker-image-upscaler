-- DDL script for runpod-worker-image-upscaler
-- PostgreSQL

CREATE TABLE IF NOT EXISTS runpod_worker_upscaled_images (
    id               SERIAL          PRIMARY KEY,
    job_id           TEXT,
    processing_time  DOUBLE PRECISION,
    original_url     TEXT            NOT NULL,
    output_url       TEXT            NOT NULL,
    scale            INTEGER         NOT NULL,
    original_width   INTEGER         NOT NULL,
    original_height  INTEGER         NOT NULL,
    output_width     INTEGER         NOT NULL,
    output_height    INTEGER         NOT NULL,
    created_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

ALTER TABLE runpod_worker_upscaled_images
    ADD COLUMN IF NOT EXISTS job_id TEXT;

ALTER TABLE runpod_worker_upscaled_images
    ADD COLUMN IF NOT EXISTS processing_time DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_runpod_worker_upscaled_images_created_at
    ON runpod_worker_upscaled_images (created_at DESC);
