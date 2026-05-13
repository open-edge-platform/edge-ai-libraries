# Text To Speech

FastAPI service for text-to-speech generation with OpenVINO and PyTorch runtime support.

## Start Here

This page is intentionally brief. Use the links below for the actual run steps, configuration details, and API examples.

- Run in Docker: [docs/run-container.md](docs/run-container.md)
- Run on the host: [docs/run-standalone.md](docs/run-standalone.md)
- Change configuration: [docs/configuration.md](docs/configuration.md)
- API use cases and examples: [docs/api.md](docs/api.md)

## What It Does

The service accepts text input, synthesizes speech with the configured TTS model, and returns either raw WAV audio or JSON metadata plus a base64-encoded WAV payload.

It supports:

- Speech generation API at `POST /v1/audio/speech`
- Voice and model metadata at `GET /v1/audio/voices`
- Health check at `GET /health`
- OpenVINO and PyTorch runtimes for supported models
- Persisted outputs under `storage/<session_id>/` when enabled

## Notes

- Do not use this page as the run guide; use the linked docs above.
- First startup can be slow because model download or conversion may happen during startup.
