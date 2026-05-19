# Overview

The Text To Speech microservice is a FastAPI-based service for synthesizing
speech from text. It accepts a text input, runs the configured TTS model
(OpenVINO or PyTorch runtime), and returns either raw WAV audio or JSON
metadata plus a base64-encoded WAV payload.

## Key Capabilities

- Speech generation API at `POST /v1/audio/speech`
- Voice and model metadata at `GET /v1/audio/voices`
- Health check at `GET /health`
- TTS runtimes: `openvino`, `pytorch`
- Configurable device (`CPU`, `GPU`, `NPU`) and precision (`int8`, `int4`,
  `fp16`, `fp32`) where supported by the runtime/model
- English-only synthesis in the current service build
- Optional persistence of synthesized output under `storage/<session_id>/`

## Storage

When `pipeline.persist_outputs` is enabled, the synthesized WAV and its
metadata are written under `storage/<session_id>/`. The session id is also
returned in the `X-Session-ID` response header for `wav` responses.

## Deployment Modes

- Containerized via Docker Compose, exposing the API on port `8011`.
- Standalone Python execution on the host, bound to `127.0.0.1:8011` by
  default.

For deeper context on internal flow and components, see
[how-it-works.md](how-it-works.md).
