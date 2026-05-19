# Release Notes

This page tracks notable changes to the Text To Speech microservice.

## Unreleased

- Initial documentation set added: overview, get-started, how-it-works,
  system-requirements, build-from-source, api-reference, troubleshooting.
- README restructured to follow the standard microservice documentation
  template, mirroring the Audio Analyzer layout for uniformity.

## Current Capabilities

- Speech generation API at `POST /v1/audio/speech`.
- Voice and model metadata at `GET /v1/audio/voices`.
- Health check at `GET /health`.
- TTS runtimes: `openvino` and `pytorch`.
- Configurable device (`CPU`, `GPU`, `NPU`) and precision (`int8`, `int4`,
  `fp16`, `fp32`) where supported by the runtime/model.
- Optional persistence of synthesized output to `storage/<session_id>/`.

## Known Limitations

- English-only synthesis. Requests with any other language are rejected
  with HTTP `400`.
- The `model` request field is accepted for OpenAI API compatibility but
  is ignored; the service always uses the model defined in `config.yaml`.
- For SpeechT5, the `voice` and `language` fields are accepted but
  ignored; the model uses a single fixed speaker embedding.
