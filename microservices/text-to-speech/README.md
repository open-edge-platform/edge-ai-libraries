# Text To Speech Microservice

This repository provides a FastAPI-based microservice for text-to-speech
generation with OpenVINO and PyTorch runtime support. It accepts text input,
synthesizes speech with the configured TTS model, and returns either raw WAV
audio or JSON metadata plus a base64-encoded WAV payload.

Below, you'll find links to detailed documentation to help you get started,
configure, and deploy the microservice.

## Documentation

- Getting Started

	- [Run in Docker](docs/run-container.md): Step-by-step guide to running
		the microservice in a container.
	- [Run on the Host](docs/run-standalone.md): Step-by-step guide to
		running the microservice directly on the host.

- Deployment

	- [Configuration](docs/configuration.md): Instructions for changing the
		microservice configuration.

- API Reference

	- [API Reference](docs/api.md): Endpoint details and request examples for
		speech generation, voice metadata, and health checks.

## Capabilities

- Speech generation API at `POST /v1/audio/speech`
- Voice and model metadata at `GET /v1/audio/voices`
- Health check at `GET /health`
- OpenVINO and PyTorch runtimes for supported models
- English-only synthesis for the current service build
- Persisted outputs under `storage/<session_id>/` when enabled

## Notes

- Do not use this page as the run guide; use the linked docs above.
- First startup can be slow because model download or conversion may happen during startup.
