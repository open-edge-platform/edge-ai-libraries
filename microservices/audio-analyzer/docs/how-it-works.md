# How It Works

This page describes the internal flow of an audio request through the
microservice.

## Request Flow

1. **Upload** — A client sends an audio file to either
   `POST /v1/audio/transcriptions` (single response) or
   `POST /v1/audio/transcriptions/stream` (NDJSON event stream).
2. **Session resolution** — If `session_id` is supplied, the service reuses
   the existing session directory under `storage/<session_id>/`. Otherwise it
   creates a new session and returns the id in the `X-Session-ID` response
   header.
3. **Preprocessing** — FFmpeg decodes the upload and produces audio chunks
   under the configured `audio_preprocessing.chunk_dir`. Chunk size, silence
   detection, and optional denoising are controlled by the
   `audio_preprocessing` config section.
4. **ASR inference** — Each chunk is transcribed by the configured ASR
   backend (`openai` or `openvino`) on the configured device (typically
   `CPU`, optionally `GPU` for supported OpenVINO paths).
5. **Sentiment (optional)** — When `sentiment.enabled` is true, the
   service runs the configured sentiment model (`openvino` or `pytorch`) and
   aggregates a session-level summary.
6. **Response** — The non-streaming endpoint returns a final response object;
   the streaming endpoint emits `transcription.chunk` events as each chunk
   completes and a final `transcription.completed` event.
7. **Cleanup** — If `pipeline.delete_chunks_after_use` is true, temporary
   chunk files are removed after processing. Session metadata remains under
   `storage/<session_id>/`.

## Components

- `api/` — FastAPI routers for transcription, health, and device listing.
- `pipeline.py` — Orchestrates preprocessing, ASR, and sentiment.
- `components/` — Backend implementations for ASR and sentiment providers.
- `utils/` — Audio utilities, config loading, and session helpers.
- `dto/` — Request and response data models.

## Configuration Surface

All runtime behavior is driven by `config.yaml` (or `config.container.yaml`
for Docker), with overrides via `AUDIO_ANALYZER_CONFIG_OVERRIDE_PATHS` and
`AUDIO_ANALYZER__...` environment variables. See
[configuration.md](configuration.md) for the full list of fields.
