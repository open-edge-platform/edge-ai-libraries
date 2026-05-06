# Audio Analyzer

FastAPI service for audio transcription and optional voice-sentiment analysis.

## Start Here

This page is intentionally brief. Use the links below for the actual run steps, configuration details, and API examples.

- Run in Docker: [docs/run-container.md](docs/run-container.md)
- Run on the host: [docs/run-standalone.md](docs/run-standalone.md)
- Change configuration: [docs/configuration.md](docs/configuration.md)
- API use cases and examples: [docs/api.md](docs/api.md)

## What It Does

The service accepts an uploaded audio file, chunks it with FFmpeg, runs ASR on each chunk, and returns either a single transcription response or a streaming NDJSON event stream. When sentiment is enabled, it also returns a session-level sentiment summary.

It supports:

- OpenAI-style transcription API at `POST /v1/audio/transcriptions`
- Streaming transcription API at `POST /v1/audio/transcriptions/stream`
- Health check at `GET /health`
- ALSA input device listing at `GET /devices`
- ASR backends: `openai`, `openvino`. (`whispercpp` to be added)
- Optional sentiment analysis with `openvino` or `pytorch`
- Session continuation by reusing `session_id`

Session data is stored under `storage/<session_id>/`.

## Notes

- Do not use this page as the run guide; use the linked docs above.
- The service exposes `X-Session-ID`; clients should read it if they want multi-upload sessions.

