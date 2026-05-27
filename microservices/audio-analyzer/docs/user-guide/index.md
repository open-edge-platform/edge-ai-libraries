# Audio Analyzer

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/audio-analyzer">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/audio-analyzer/README.md">
     Readme
</div>
hide_directive-->

The Audio Analyzer is a microservice that turns spoken audio into text and,
optionally, into a high-level sentiment summary. It is designed to be dropped
into voice-enabled applications (kiosks, assistants, call analytics, meeting
notes) where a simple HTTP upload should return either a final transcript or
a live stream of partial results.

## Use Cases

- Conversational assistants and kiosks that need speech-to-text on the edge.
- Post-call or meeting analytics where a session-level sentiment summary is
  useful alongside the transcript.
- Batch transcription of recorded audio files.
- Streaming transcription UIs that consume incremental NDJSON events as
  chunks complete.

## Key Capabilities

- OpenAI-style transcription endpoint and a streaming NDJSON variant.
- Multi-backend ASR (OpenAI Whisper, OpenVINO, with whisper.cpp planned).
- Optional voice-sentiment analysis aggregated per session.
- Session continuation so multiple uploads can extend the same conversation.
- Runs on CPU; supports GPU acceleration on Intel hardware via OpenVINO.

## Supported Models

**ASR (speech-to-text):**

- Whisper family — `whisper-tiny`, `whisper-base`, `whisper-small`,
  `whisper-medium`, `whisper-large` — selectable via `models.asr.name`.
- Backends: `openai` (PyTorch), `openvino` (Intel-optimized).

**Sentiment (optional, voice-based):**

- Default: `speechbrain/emotion-recognition-wav2vec2-IEMOCAP`.
- Any compatible HuggingFace model can be configured via `sentiment.model`,
  served through the `openvino` or `pytorch` provider.

## Next Steps

- See [get-started.md](./get-started.md) for a step-by-step guide to your first run.
- See [configuration.md](./get-started/configuration.md) for how to select models, devices,
and precision.
- See [how-it-works.md](./how-it-works.md) for the internal request flow.

<!--hide_directive
:::{toctree}
:hidden:

./get-started.md
./how-it-works.md
./api-reference.md
./troubleshooting.md
Release Notes <./release-notes.md>

:::
hide_directive-->
