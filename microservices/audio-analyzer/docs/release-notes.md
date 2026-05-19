# Release Notes

This page tracks notable changes to the Audio Analyzer microservice.

## Unreleased

- Initial documentation set added: overview, get-started, how-it-works,
  system-requirements, build-from-source, api-reference, troubleshooting.
- README restructured to follow the standard microservice documentation
  template.

## Current Capabilities

- OpenAI-style transcription API at `POST /v1/audio/transcriptions`.
- Streaming transcription API at `POST /v1/audio/transcriptions/stream`.
- Health check at `GET /health` and ALSA device listing at `GET /devices`.
- ASR backends: `openai`, `openvino`.
- Optional sentiment analysis with `openvino` or `pytorch`.
- Session continuation via `session_id` (returned in `X-Session-ID`).

## Known Limitations

- `whispercpp` ASR backend is planned but not yet available.
- The `prompt` form field on `POST /v1/audio/transcriptions` is accepted but
  currently ignored.
