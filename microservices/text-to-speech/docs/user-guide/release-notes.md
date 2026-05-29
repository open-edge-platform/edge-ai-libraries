# Release Notes: Text To Speech

This page tracks releases of the Text To Speech microservice. The most
recent release is listed first; older entries are preserved for history.

## v1.0.0

Initial release of the Text To Speech microservice: an
OpenAI-API-compatible speech synthesis service with multi-runtime support
and selectable models, built for edge deployment on Intel hardware.

**New**

- OpenAI-compatible speech endpoint (`POST /v1/audio/speech`) returning
  either raw `audio/wav` or a JSON envelope with metadata and a
  base64-encoded WAV payload.
- Voice and model metadata endpoint (`GET /v1/audio/voices`) for client
  discovery of available speakers.
- Multi-runtime TTS backends: `openvino` (Intel-optimized) and `pytorch`.
- Supported models: SpeechT5 (`microsoft/speecht5_tts`) and Qwen3-TTS
  (`Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`) with `custom_voice` and
  `voice_design` variants.
- Configurable device (`CPU`, `GPU`, `NPU`) and precision (`int8`, `int4`,
  `fp16`, `fp32`) where supported by the runtime/model.
- Optional persistence of synthesized output to `storage/<session_id>/`
  with `X-Session-ID` returned in the response headers.
- Health endpoint (`GET /health`) for readiness probes.
- Models are warm-loaded once per process and reused across requests to
  keep per-request synthesis latency low.
- OpenVINO acceleration on Intel CPUs, integrated/discrete GPUs, and NPUs.
- Single `config.yaml` shared by standalone and container runs, with env
  overrides via `TEXT_TO_SPEECH__...`.
- Docker Compose deployment exposing the API on port `8011`; standalone
  Python mode binds `127.0.0.1:8011` on the host.
- Container runs as a non-root user (UID 1000).

**Known issues**

- English-only synthesis. Requests with any other language are rejected
  with HTTP `400`.
- The `model` request field is accepted for OpenAI API compatibility but
  is ignored; the service always uses the model defined in `config.yaml`.
- For SpeechT5, the `voice` and `language` fields are accepted but
  ignored; the model uses a single fixed speaker embedding.
- Compatibility with the Video Search and Summarization sample
  application will be added in a subsequent release.
