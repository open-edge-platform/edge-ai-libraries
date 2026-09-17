<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Voice Conversion

The Voice page at `/voice` converts a recording to text or text to WAV audio.
Each request is independent. No conversation, previous transcript, LLM, or
kiosk-core is involved. Only the latest result in each tab is held in browser
memory; navigating away clears it. Models remain loaded across requests.

## Deployment

Run from the ViPPET component directory. The Makefile detects the hardware
profile using the standard environment setup and applies the matching voice
hardware overrides. To pull published images and start ViPPET with voice
services without building any images:

```bash
make pull-voice
make run-voice
```

`make run` executes `env-setup`, loads `.env`, and runs the original `up -d`
with the base and detected hardware Compose files plus STT/TTS overrides.
It preserves Compose's normal image pull/build behavior, including local builds
when needed. `make run-voice` uses the same files but explicitly passes
`--no-build`: an unavailable image produces an error instead of falling back
to a local build. Existing local images can also be used without pulling first.
`make stop` and `make stop-voice` stop and remove the stack's containers,
including STT/TTS, using the same Compose files as startup. Both preserve named
volumes and use the existing `.env` without rerunning `env-setup`.
Direct Compose usage without `compose.voice.yml`
still starts only the base application.

The Makefile defines and exports `AUDIO_ANALYZER_TAG` and `TEXT_TO_SPEECH_TAG`,
both defaulting to `2026.1.0`. Plain `make pull-voice` and `make run` use
these defaults without any shell variable setup. Change the defaults in the
Makefile or override them independently on the command line, for example:

```bash
make pull-voice run AUDIO_ANALYZER_TAG=2026.2.0 TEXT_TO_SPEECH_TAG=2026.2.0
```

Command-line values override inherited environment values and Makefile defaults.
The selected tags must exist in the registry. Unset or empty tag variables use
`2026.1.0`. Full image overrides remain available and take precedence over tags:

- `AUDIO_ANALYZER_IMAGE=docker.io/intel/audio-analyzer:2026.1.0`
- `TEXT_TO_SPEECH_IMAGE=docker.io/intel/text-to-speech:2026.1.0`

Export these variables in the shell to select another version, registry, or
image digest. Do not store overrides in `.env` when using Make: the standard
`env-setup` prerequisite regenerates that file. ViPPET images still use the existing
`DOCKER_TAG`. The selected backend/UI images must already contain the Voice
feature; pulling an older ViPPET release will not add local source changes.
Registry manifest availability has been checked for the default audio tags;
their runtime compatibility with this configuration must be verified on the
target deployment.

For direct Compose usage, select a matching hardware profile, for example CPU:

```bash
COMPOSE_PROFILES=cpu docker compose -f compose.yml -f compose.cpu.yml \
  -f compose.voice.yml up -d --no-build
```

To pull and start only the audio services alongside an already updated ViPPET:

```bash
COMPOSE_PROFILES=cpu docker compose -f compose.yml -f compose.cpu.yml -f compose.voice.yml pull \
  audio-analyzer text-to-speech
COMPOSE_PROFILES=cpu docker compose -f compose.yml -f compose.cpu.yml -f compose.voice.yml up -d --no-deps \
  --no-build audio-analyzer text-to-speech
COMPOSE_PROFILES=cpu docker compose -f compose.yml -f compose.cpu.yml -f compose.voice.yml ps \
  audio-analyzer text-to-speech
```

Local builds remain available explicitly with `make build-voice`, followed by
`make run-voice`. They use this repository's microservice Dockerfiles and tag
the results with the configured image names. Use distinct local image tags to
avoid overwriting cached release images; a later pull replaces local images
under the same tag. No sibling kiosk checkout is needed.

The services are reachable inside the Compose network and through host ports
`127.0.0.1:8010` (audio-analyzer) and `127.0.0.1:8011` (text-to-speech).
No host microphone devices are exposed; the browser captures recordings.
The base application does not depend on their health. Without these services,
conversion requests report unavailability while other ViPPET features work.

Export `AUDIO_ANALYZER_PORT` and `TEXT_TO_SPEECH_PORT` to change the host ports
without changing container ports or the backend service URLs. Export
`VOICE_BIND_ADDRESS` to change the bind address. For example, to avoid conflicts:

```bash
export AUDIO_ANALYZER_PORT=18010 TEXT_TO_SPEECH_PORT=18011
make run-voice
```

### GPU and NPU

The configuration uses Whisper Base and SpeechT5 with OpenVINO. Make selects
the following voice overrides for the detected ViPPET hardware profile:

| Profile | Additional voice files after `compose.voice.yml` | ASR | TTS       |
| ------- | ------------------------------------------------ | --- | --------- |
| `cpu`   | None                                             | CPU | CPU, INT8 |
| `gpu`   | `compose.voice.gpu.yml`                          | GPU | GPU, FP16 |
| `npu`   | `compose.voice.npu.yml`                          | NPU | GPU, FP16 |

The GPU override gives both services `/dev/dri` and the host's numeric
`RENDER_GROUP_ID` as a supplementary group. The NPU override gives
audio-analyzer `/dev/accel`, the `NPU_GROUP_ID` group (defaulting to
`RENDER_GROUP_ID`), and `ZE_ENABLE_ALT_DRIVERS=libze_intel_npu.so`, while
text-to-speech gets `/dev/dri` and `RENDER_GROUP_ID` for GPU inference.
The host must have the corresponding device nodes and compatible drivers;
the images must include the required OpenVINO runtimes. No privileged mode or
extra Linux capabilities are enabled.

`setup_env.sh` detects `RENDER_GROUP_ID` for Make. When invoking Compose
directly, set it to the host render group's numeric ID. If NPU device nodes
belong to a different group, export their numeric group ID as `NPU_GROUP_ID`.
For example, inspect it with `stat -c '%g' /dev/accel/accel0`.

Direct GPU startup:

```bash
export RENDER_GROUP_ID=$(getent group render | cut -d: -f3)
COMPOSE_PROFILES=gpu docker compose -f compose.yml -f compose.gpu.yml \
  -f compose.voice.yml -f compose.voice.gpu.yml up -d --no-build
```

Direct NPU startup (use the NPU voice override instead of the GPU override):

```bash
export RENDER_GROUP_ID=$(getent group render | cut -d: -f3)
COMPOSE_PROFILES=npu docker compose -f compose.yml -f compose.npu.yml \
  -f compose.voice.yml -f compose.voice.npu.yml \
  up -d --no-build
```

Export `VOICE_ASR_DEVICE` (`CPU`, `GPU`, or `NPU`), `VOICE_TTS_DEVICE` (`CPU` or
`GPU`), and `VOICE_TTS_DTYPE` to override inference settings. Device selection
alone does not expose hardware: keep the corresponding Compose overrides.
To run ASR on GPU, use the GPU voice override, including on an NPU-capable host.
SpeechT5 does not document NPU support, so the NPU profile deliberately uses
GPU for TTS. For CPU inference on an accelerator host, export
`VOICE_ASR_DEVICE=CPU VOICE_TTS_DEVICE=CPU VOICE_TTS_DTYPE=int8`.
The `gpu-wsl` profile leaves voice inference on CPU; these Linux hardware
overrides do not implement WSL device passthrough.

Diarization and sentiment analysis are disabled; SpeechT5 uses Ryan's voice.
TTS supports English in this configuration. Changing a language label alone
does not add multilingual synthesis support.

First startup downloads/exports models and requires network access to model
sources. Healthchecks allow 15 minutes for startup. Subsequent starts reuse
named model/cache volumes. Configure `http_proxy`, `https_proxy`, and `no_proxy`
as required. Do not pass tokens through Docker build arguments.

To stop only the optional services, preserving their caches:

```bash
COMPOSE_PROFILES=cpu docker compose -f compose.yml -f compose.cpu.yml -f compose.voice.yml stop \
  audio-analyzer text-to-speech
```

For GPU/NPU, use the same profile and override files as at startup.

## Browser and Input Requirements

- Microphone capture requires HTTPS or `localhost`, permission to use the
  microphone, and browser support for MediaRecorder and Web Audio.
- Recording stops automatically after 60 seconds and is converted in the
  browser to mono PCM 16-bit WAV at 16 kHz. Uploaded WAV must be mono PCM
  16-bit, 8-48 kHz, at most 60 seconds and 10 MiB.
- Select a recognition language for STT. Default: English.
- TTS input must contain 1-5000 characters after trimming whitespace.
- Playback is explicit using the audio controls. Generated WAV can be downloaded.
- The STT source section offers microphone recording and WAV upload. The selected
  audio preview and transcription appear below the source controls.
- The TTS **Sample text** menu fills the text input with an editable example.
  Selecting a sample clears the previous generated audio and its request metrics.
- Audio previews display a waveform sampled from the actual decoded audio,
  using browser Web Audio and the existing Recharts library. No audio is sent
  to an additional visualization service. Waveforms are approximate amplitude
  overviews, not interactive seek controls; use the native audio player to seek.
  If visualization fails, playback and WAV download remain available.
- Voice uses the existing semantic color tokens, typography, shadcn controls
  and metrics components in both light and dark themes. Global navigation is
  unchanged. No model, device, voice or synthesis-rate selectors are added;
  those settings remain service configuration. MP3 and bundled sample recordings
  are not supported by this UI.
- Cancel aborts the browser request or recording; it does not guarantee that
  already-started inference in the upstream service stops immediately.

## API

`POST /api/v1/voice/transcriptions` accepts multipart `file` and optional
two-letter `language` (default `en`). It returns `{"text": "..."}`.
No upstream `session_id`, history, or prompt is forwarded.

`POST /api/v1/voice/speech` accepts `{"input": "Hello world"}` and returns
`audio/wav`. The model and voice come from service configuration.

Backend service locations are configured with `AUDIO_ANALYZER_URL` (default
`http://audio-analyzer:8010`) and `TEXT_TO_SPEECH_URL` (default
`http://text-to-speech:8011`). They must be deployment-controlled URLs, never
user-provided targets. Internal service calls bypass environment HTTP proxies.

The adapter uses a 5-second connection timeout and a 120-second total upstream
deadline. Responses are limited to 128 KiB for STT and 64 MiB for TTS.
Invalid input returns 400/422; oversized audio returns 413; invalid upstream
responses return 502; unavailable/busy services return 503; timeouts return 504.
Upstream error bodies are not forwarded. Nginx limits voice request bodies to
11 MiB, including multipart overhead, and disables response caching.

## Metrics

Each successful conversion displays its own timing cards, reusing the existing
ViPPET metrics UI. STT and TTS retain separate results in their respective tabs.

| Metric             | Unit | Measurement interval                                                                            |
| ------------------ | ---- | ----------------------------------------------------------------------------------------------- |
| Request duration   | ms   | Browser fetch start through receipt and parsing of the complete JSON or WAV response.           |
| Service round trip | ms   | ViPPET proxy start of the upstream POST through receipt of the complete upstream response body. |

Both intervals use monotonic clocks. Request duration includes upload, proxy
processing, the service call, download and browser response parsing; it excludes
microphone recording, WAV preparation and playback. Service round trip includes
connection setup, transport, service queueing and processing. Neither is a pure
model inference measurement or time to first byte/token. Startup/model loading
can increase the observed duration. The values are not aggregated benchmarks.

Both successful API responses include `X-Voice-Service-Duration-Ms`, a decimal
number in milliseconds, for example `250.000`. JSON and WAV bodies are unchanged.
Failures do not include this success metric. No `/v1/performance` polling is used:
the services' global `last_ms` cannot reliably identify a particular request.

The previous result and its timings are cleared when the input or recognition
language changes, a new recording starts, or a replacement conversion starts.
Failed or cancelled requests do not publish results or timings. Switching tabs
preserves completed results but cancels any pending request. Missing or invalid
service timing headers show "Service round trip unavailable" while conversion
and the browser-side duration remain available, including with older backends.

Expand **Platform metrics (system-wide)** to use the existing live metrics
dashboard for CPU, memory, GPU and available NPU telemetry. Video FPS and pipeline
latency are hidden in Voice. These charts represent the whole platform, including
other workloads, not isolated STT/TTS utilization or a snapshot of the conversion.
They use the existing metrics-manager stream and do not start extra service polls.

## Storage and Security

ViPPET does not store or log recording contents, sentences, or transcripts.
Both adapter responses use `Cache-Control: no-store`. TTS output persistence
is disabled. Audio-analyzer still writes recordings/transcripts into its
dedicated `voice_asr_storage` volume, clears storage on service startup, and
deletes processed chunks. There is no automatic per-request retention deadline.
This is not a zero-retention deployment; arrange storage cleanup according to
your data policy before using sensitive recordings. Removing model/cache volumes
is not necessary to clear session data.

Deployment owners must provide HTTPS, access control, request-rate limits, and
appropriate retention. The published audio ports expose upstream APIs directly,
bypassing ViPPET's proxy validation and limits. Keep the default loopback bind
unless network access is protected by appropriate access control and TLS.

## Verification

```bash
PYTHONPATH=vippet .venv/bin/python -m unittest discover \
  -s vippet/tests/unit/api_tests -p voice_test.py -v
```

Start the UI development server, then run the browser checks in another terminal:

```bash
cd ui
npm run dev -- --host 127.0.0.1
# In another terminal, from ui/:
npx playwright install chromium
npx playwright test tests/voice.spec.ts
```

Set `VOICE_UI_URL` when the server uses another port. Browser tests mock service
responses and use a synthetic microphone; they do not validate model quality.
