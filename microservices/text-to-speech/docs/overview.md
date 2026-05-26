# Overview

The Text To Speech microservice turns text into natural-sounding speech. It
is designed to be dropped into voice-enabled applications (kiosks,
assistants, IVR, accessibility tooling) where a simple HTTP request should
return either raw WAV audio or a JSON payload with metadata.

## Use Cases

- Voice responses for conversational assistants and kiosks.
- Accessibility readers and announcement systems.
- IVR / call-flow prompts generated on the edge.
- Audio generation pipelines that need a self-hosted, OpenAI-compatible
  `/v1/audio/speech` endpoint.

## Key Capabilities

- OpenAI-style speech endpoint and a voices/metadata endpoint.
- Multi-runtime backends: OpenVINO (Intel-optimized) and PyTorch.
- Configurable device (`CPU`, `GPU`, `NPU`) and precision (`int8`, `int4`,
  `fp16`, `fp32`) where the runtime/model supports it.
- Selectable speaker / voice per model family.
- Optional persistence of synthesized output for session reuse.

## Supported Models

- **SpeechT5** — `microsoft/speecht5_tts` (default). Lightweight,
  English-only, well suited for CPU and edge devices.
- **Qwen3-TTS** — `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` with
  `model_variant: custom_voice` or `voice_design` for richer voice control.
- Runtimes: `openvino` (recommended on Intel hardware) and `pytorch`.
- English-only synthesis in the current service build.

See [configuration.md](configuration.md) for how to select the model,
runtime, device, precision, and default speaker, and
[how-it-works.md](how-it-works.md) for the internal request flow.
