# Audio Analyzer

FastAPI service for audio transcription and optional voice-sentiment analysis.

## Overview

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

## Docs

- Run with Docker Compose: [docs/run-container.md](docs/run-container.md)
- Run directly without Docker: [docs/run-standalone.md](docs/run-standalone.md)
- Configuration reference: [docs/configuration.md](docs/configuration.md)
- API use cases, examples, and endpoint reference: [docs/api.md](docs/api.md)

## Requirements

Minimum runtime requirements:

- Python 3.12
- `ffmpeg`
- `libsndfile`
- Enough disk space for model exports and session storage

## Storage Layout

Important runtime directories:

- `models/`: downloaded and exported model artifacts
- `chunks/`: temporary FFmpeg chunk files
- `storage/<session_id>/`: per-session uploads and outputs

Typical session files:

- uploaded audio files
- `transcription.txt`
- `timestamped_transcription.txt`
- `session_state.json`

## Notes

- First startup can be slow because model download/export happens during startup.
- The current container and direct-run paths are both supported and validated.
- The service exposes `X-Session-ID`; make sure your client reads it if you want multi-upload sessions.
- OpenVINO ASR is working, but short-clip quality can still vary by input and model choice.

