# Release Notes: Audio Analyzer

This page tracks releases of the Audio Analyzer microservice. The most
recent release is listed first; older entries are preserved for history.

## v1.4.0

First release of the Audio Analyzer as a self-contained,
OpenAI API-compatible speech-to-text microservice with optional voice
sentiment analysis, built for edge deployment on Intel hardware.

**New**

- OpenAI-compatible transcription API (`POST /v1/audio/transcriptions`)
  and a streaming NDJSON variant (`/stream`).
- Multi-backend ASR: `openai` (PyTorch Whisper) and `openvino`
  (Intel-optimized); `whispercpp` planned for a follow-up release.
- Full Whisper model family supported (`tiny` → `large`).
- Optional voice sentiment analysis with session-level aggregation
  (`openvino` or `pytorch` provider).
- FFmpeg-based preprocessing: chunking, silence detection, optional
  RNNoise denoising.
- Session continuation via `session_id` (returned in `X-Session-ID`).
- Health (`/health`) and ALSA device listing (`/devices`) endpoints.

**Improved**

- OpenVINO CPU/GPU acceleration on Intel hardware; models warm-loaded
  once per process.
- Layered config (`config.yaml`, env overrides via
  `AUDIO_ANALYZER__...`) and Docker Compose deployment on port `8010`.
- Container now runs as a non-root user (UID 1000).

**Known issues**

- `whispercpp` backend is wired into configuration but not yet
  enabled at runtime.
- The `prompt` form field is accepted for API compatibility but
  currently ignored.
- Compatibility with the Video Search and Summarization sample
  application will be added in a subsequent release.

## v1.3.1

- Released as part of `release-2026.0.0`.
- Supported features based on the requirements of the Video Search and
  Summarization sample application. Refer to that sample's release notes
  for details on this microservice at that version.
