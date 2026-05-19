# Overview

The Audio Analyzer is a FastAPI-based microservice for audio transcription and
optional voice-sentiment analysis. It accepts an uploaded audio file, chunks
it with FFmpeg, runs ASR on each chunk, and returns either a single
transcription response or a streaming NDJSON event stream. When sentiment is
enabled, it also returns a session-level sentiment summary.

## Key Capabilities

- OpenAI-style transcription API at `POST /v1/audio/transcriptions`
- Streaming transcription API at `POST /v1/audio/transcriptions/stream`
- Health check at `GET /health`
- ALSA input device listing at `GET /devices`
- ASR backends: `openai`, `openvino` (`whispercpp` to be added)
- Optional sentiment analysis with `openvino` or `pytorch`
- Session continuation by reusing `session_id` (returned in `X-Session-ID`)

## Storage

Per-session runtime files are stored under `storage/<session_id>/`. Temporary
audio chunks are written under the configured `audio_preprocessing.chunk_dir`
and can be auto-deleted after processing.

## Deployment Modes

- Containerized via Docker Compose, exposing the API on port `8010`.
- Standalone Python execution on the host, bound to `127.0.0.1:8010` by
  default.

For deeper context on internal flow and components, see
[how-it-works.md](how-it-works.md).
