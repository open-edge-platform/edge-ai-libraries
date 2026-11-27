# Release Notes: Audio Analyzer

This page tracks releases of the Audio Analyzer microservice. The most
recent release is listed first; older entries are preserved for history.

## Version 2026.3.0

**Release Date:** December 7, 2026

**New**:

- Added a per-request automatic speech recognition (ASR) device choice (`CPU`, `GPU`, or `NPU`), with a separate model cache for each device.
- Added an optional FunASR Paraformer ASR provider for Chinese and English, with ModelScope model downloads.
- Added preview transcription on the realtime WebSocket, with an optional separate preview model pool.
- Added an opt-in low-latency mode on the realtime WebSocket that reuses the final preview at commit (about 30% lower voice-to-voice latency).
- Added model provisioning through the shared Model Download service, with direct download as a fallback.
- Added a per-request flag to turn diarization off.
- Added optional loudness normalization.

**Improved**:

- Reduced ASR latency by about 50% on short audio chunks by cutting per-request overhead, such as `ffprobe` and `ffmpeg` calls.
- Sped up responses by caching the OpenVINO™ device check.
- Fixed Whisper timestamps on NPU.
- Fixed FunASR startup on Python 3.12 and diarization startup with torchaudio 2.11 (speechbrain 1.1.2).
- Moved to an Ubuntu-based Docker image and resolved image CVEs.
- Updated OpenVINO™ and OpenVINO™ GenAI to 2026.3.1 and Level Zero to 1.34.0.
- Updated image tags to the 2026.3.0-rc1 release.
- Updated documentation, including benchmark results and skill files.

## Version 2026.2.0

**Release Date:** September 9, 2026

**New:**

- OpenAI-compatible streaming transcription over Server-Sent Events (SSE),
  including incremental transcript events and completion signaling.
- Realtime WebSocket transcription API for low-latency, bidirectional PCM16
  audio streaming with server-side VAD and incremental transcription events.
- VSS-compatible transcription APIs and response formats, including `/models`
  and `/transcriptions` compatibility routes.
- OpenVINO NPU support for ASR, validated with Whisper Tiny and Whisper Base,
  with CPU, GPU, and NPU device selection.
- OpenVINO-backed speaker diarization with GPU and NPU support.

**Improved:**

- Multi-speaker detection now independently analyzes Whisper segments,
  improving secondary-speaker detection in single-microphone kiosk scenarios.
- Speaker enrollment persistence using `speaker_scope_id`, allowing speaker
  identity to persist across requests and service restarts.
- Documented and standardized the supported ASR provider/device matrix across
  OpenAI, Whisper.cpp, and OpenVINO providers.

## Version 1.4.0

First release of the Audio Analyzer as a self-contained,
OpenAI API-compatible speech-to-text microservice with optional voice
sentiment analysis, built for edge deployment on Intel hardware.

**Release Date:** June 17, 2026

**New:**

- OpenAI-compatible transcription API (`POST /v1/audio/transcriptions`)
  and a streaming NDJSON variant (`/stream`).
- Multi-backend ASR: `openai` (PyTorch Whisper), `openvino`
  (Intel-optimized), and `whispercpp` (CPU-only).
- Full Whisper model family supported (`tiny` → `large`).
- Optional voice sentiment analysis with session-level aggregation
  (`openvino` or `pytorch` provider).
- FFmpeg-based preprocessing: chunking, silence detection, optional
  RNNoise denoising.
- Session continuation via `session_id` (returned in `X-Session-ID`).
- Health (`/health`) and ALSA device listing (`/devices`) endpoints.
- New User Guide doc set, including: overview, get-started, how-it-works  configuration, api-reference, and troubleshooting Markdown files, plus an architecture diagram and a restructured README.md.

**Improved:**

- OpenVINO CPU/GPU acceleration on Intel hardware; models warm-loaded
  once per process.
- Layered config (`config.yaml`, env overrides via
  `AUDIO_ANALYZER__...`) and Docker Compose deployment on port `8010`.
- Container now runs as a non-root user (UID 1000).

**Known issues:**

- The `prompt` form field is accepted for API compatibility but
  currently ignored.
- Compatibility with the Video Search and Summarization sample
  application will be added in a subsequent release.

## Version 1.3.1

**Release Date:** April 2026

**New:**

- Released as part of `release-2026.0.0`.
- Supported features based on the requirements of the Video Search and
  Summarization sample application. Refer to that sample's release notes
  for details on this microservice at that version.
