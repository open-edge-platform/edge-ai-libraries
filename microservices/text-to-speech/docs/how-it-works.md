# How It Works

This page describes the internal flow of a TTS request through the
microservice.

## Request Flow

1. **Request** — A client sends a JSON body to `POST /v1/audio/speech` with
   the text to synthesize and an optional `voice`, `language`,
   `instructions`, and `response_format`.
2. **Validation** — The service validates the request, enforces the English
   language constraint, and resolves the speaker against the configured
   voices.
3. **Model load / warmup** — On first use, the configured TTS model is
   loaded according to `models.tts.runtime` (`openvino` or `pytorch`) on the
   configured `device` (`CPU`, `GPU`, or `NPU`) and `dtype`. Subsequent
   requests reuse the warmed-up pipeline.
4. **Synthesis** — The pipeline generates a WAV waveform from the input
   text using the chosen model and speaker embedding.
5. **Response** — When `response_format=wav`, the service returns raw
   `audio/wav` with `X-Session-ID` in the response header. When
   `response_format=json`, it returns metadata plus a base64-encoded WAV
   payload.
6. **Persistence (optional)** — If `pipeline.persist_outputs` is true, the
   WAV and metadata are also written to `storage/<session_id>/`.

## Components

- `api/` — FastAPI routers for speech generation, voice metadata, and
  health.
- `pipeline.py` — Orchestrates model loading, warmup, and synthesis.
- `components/` — Backend implementations for the OpenVINO and PyTorch TTS
  runtimes.
- `utils/` — Audio utilities, config loading, and session helpers.
- `dto/` — Request and response data models.

## Configuration Surface

All runtime behavior is driven by `config.yaml` (or `config.container.yaml`
for Docker), with overrides via `TEXT_TO_SPEECH_CONFIG_OVERRIDE_PATHS` and
`TEXT_TO_SPEECH__...` environment variables. See
[configuration.md](configuration.md) for the full list of fields.
