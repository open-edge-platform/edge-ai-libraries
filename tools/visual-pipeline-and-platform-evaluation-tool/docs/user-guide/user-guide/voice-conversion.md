<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Audio Pipelines

The **Pipelines** page has a Vision tab and an Audio tab.
Audio includes YAML-defined **Speech to Text** and **Text to Speech** presets.
If the Audio catalog request fails, the tab shows an error.
Open either card under `/pipelines/audio/<preset-id>/<variant-id>` and run it
immediately with its managed defaults, or replace those defaults with an
upload, recording, edited text, voice, or language. The variant selector is the
inference-device selector: Speech to Text provides CPU, GPU, and NPU variants,
while Text to Speech provides CPU and GPU variants. The run button stays
disabled until the pipeline's required models are installed. The Back icon
returns to the Audio tab of the Pipelines page. Each conversion is independent.
No conversation, previous transcript, LLM, or kiosk-core is involved.

Each route renders one operation-specific workflow; there are no STT/TTS tabs.
The pipeline card opens its first variant, and the variant selector updates the
route for the same pipeline.

The Speech to Text preset uses the bundled `sample_male.wav` recording and
English. The Text to Speech preset uses the bundled 200-character demonstration
text and the Ryan voice. Preset definitions live in `vippet/pipelines/` with
`type: audio`.

Predefined recordings are listed in `shared/audio/default_recordings.yaml`. Each
entry sets `local: <file>.wav` and `filename`. The file is read from
`vippet/pipelines/recordings/` (shipped in the image) and copied to
`shared/audio/input/auto` only when the target is missing or not a valid WAV.
Nothing is downloaded at startup.

Every Speech to Text and Text to Speech conversion started from the Audio
pipeline UI runs as a managed job. This includes uploaded or recorded audio,
edited text, and another voice. Each successful TTS job publishes a UUID-named
WAV file under `shared/audio/output`, which the browser downloads or plays.
Accepted managed Audio runs appear under **Jobs > Audio** at `/jobs/audio`.

## Deployment

Run from the ViPPET component directory. The Makefile detects the hardware
profile using the standard environment setup and applies the matching voice
hardware overrides. Build and start the complete application with the standard
lifecycle:

```bash
make build
make run
```

When an Audio pipeline's required catalog model is missing, ViPPET opens the
existing model-install dialog for that specific model: **Whisper Base** for
Speech to Text or **SpeechT5** for Text to Speech. Conversion remains disabled
until the model status is Installed. Installing these catalog entries does not
provision the models that the Voice services run; see
[Model provisioning](#model-provisioning) and
[Known limitations](#known-limitations).

`make build` and `make run` execute `env-setup`, load `.env`, and combine the
base Compose file with the detected hardware override. `make build` builds the
core ViPPET images only; the Voice services have no build section in
`compose.yml`. `make run` starts the complete service set with Compose's normal
image behavior, pulling the published Voice images when they are not present
locally. `make stop` removes the core and Voice containers together while
preserving named volumes, including the Voice model volumes. It uses the
existing `.env` without rerunning `env-setup`.
`make clean-output-audio` removes generated TTS WAV files. The broader
`make clean` target is a full reset of the host-side `shared/` data:

- It removes **every installed model** under `shared/models/output`, both
  Vision models and the Voice catalog checkpoints. Afterwards, the Audio
  pipelines show their required models as not installed until you install them
  again.
- It removes the model-download cache and plugin environments under
  `shared/model-download`, so the next model installation is slower.
- It removes generated TTS WAV files and the whole `shared/audio/input` tree,
  including the installed default recordings. ViPPET copies the default
  recordings again from its image on the next start.
- It removes output videos and the `shared/videos/input` and
  `shared/videos/video-generator` trees.

`make clean` does not stop containers and does not remove named volumes, so
the models that the Voice services run (`voice_asr_models`,
`voice_tts_models`) and their caches are kept. To remove those as well, stop
the stack and delete the volumes with `docker volume rm`. Compose prefixes
volume names with the project name; list them with `docker volume ls`.

The Makefile defines and exports `AUDIO_ANALYZER_TAG` and `TEXT_TO_SPEECH_TAG`,
both defaulting to `2026.3.0-rc1`. Standard lifecycle targets use these defaults
without any shell variable setup. Override them independently on the command
line, for example:

```bash
make build run AUDIO_ANALYZER_TAG=2026.3.0-rc1 TEXT_TO_SPEECH_TAG=2026.3.0-rc1
```

Command-line values override inherited environment values and Makefile defaults.
Full image overrides remain available and take precedence over tags:

- `AUDIO_ANALYZER_IMAGE=docker.io/intel/audio-analyzer:2026.3.0-rc1`
- `TEXT_TO_SPEECH_IMAGE=docker.io/intel/text-to-speech:2026.3.0-rc1`

Export these variables in the shell to select another version, registry, or
image digest. Do not store overrides in `.env` when using Make: the standard
`env-setup` prerequisite regenerates that file. ViPPET images still use the
existing `DOCKER_TAG`.

For direct Compose usage, select a matching hardware profile, for example CPU:

```bash
COMPOSE_PROFILES=cpu docker compose -f compose.yml -f compose.cpu.yml \
  up -d --no-build
```

To pull and start only the audio services alongside an already updated ViPPET:

```bash
COMPOSE_PROFILES=cpu docker compose -f compose.yml -f compose.cpu.yml pull \
  audio-analyzer text-to-speech
COMPOSE_PROFILES=cpu docker compose -f compose.yml -f compose.cpu.yml up -d --no-deps \
  --no-build audio-analyzer text-to-speech
COMPOSE_PROFILES=cpu docker compose -f compose.yml -f compose.cpu.yml ps \
  audio-analyzer text-to-speech
```

To build the Voice images from this repository's microservice Dockerfiles, use
`make build-dev`, which adds `compose.dev.yml` and tags the results with the
configured image names. Use distinct local image tags to avoid overwriting
cached release images; a later pull replaces local images under the same tag.
No sibling kiosk checkout is needed.

### Model provisioning

Two independent download paths exist in this release:

- **Voice services (used for inference):** audio-analyzer and text-to-speech
  download their configured models from Hugging Face and export them to
  OpenVINO on their first startup. Audio Analyzer exports Whisper Base with
  `int8` weights; Text to Speech prepares SpeechT5 with `fp16`. The artifacts
  are stored in the named volumes `voice_asr_models` and `voice_tts_models` and
  reused on later starts while those volumes exist. Each service compiles the
  artifact for the selected CPU, GPU, or NPU device when it loads it.
- **ViPPET model catalog (used for the Run gate):** the **Models** page and the
  model-install dialog download the `voice-whisper-base` and `voice-speecht5`
  catalog entries through model-download. These are PyTorch checkpoints written
  under `shared/models/output/huggingface`. ViPPET marks a model Installed when
  its checkpoint file exists. The Voice services never read these files.

Neither service mounts `shared/models`. A first start therefore needs network
access to Hugging Face from the Voice containers. Until the download and export
complete, a service is not healthy; the Compose health checks allow a
15-minute start period. If the download fails, for example without network
access, the service does not become healthy and Audio jobs fail.

The services are reachable inside the Compose network and through host ports
`8010` (audio-analyzer) and `8011` (text-to-speech). The base Compose mappings
do not specify a loopback host address, so host and firewall configuration
determine whether those ports are reachable from other machines.
No host microphone devices are exposed; the browser captures recordings.
The base application does not depend on their health. Without these services,
Audio jobs end as `FAILED` while other ViPPET features work.

### Audio variants and inference devices

Each Audio pipeline exposes named variants in its YAML definition. Selecting a
variant updates the route and sends that variant's device with the conversion
request. Speech to Text supports CPU, GPU, and NPU; Text to Speech supports CPU
and GPU. There is no separate device selector or service-default variant in the
Audio pipeline UI.

Audio Analyzer and Text to Speech validate the selected device and load or
reuse a model compiled for it. The first request on a new device includes model
compilation and warm-up, so it can take substantially longer than subsequent
requests. Models loaded for multiple devices remain resident until the service
restarts.

An available variant does not guarantee that its device node is mounted in the
Voice container or that the configured provider, runtime, and model support it.
In those cases the conversion fails explicitly; it does not silently fall back
to CPU.

### GPU, NPU and WSL

The configuration uses Whisper Base and SpeechT5 with OpenVINO. Make selects
the following settings from the detected ViPPET hardware profile:

| Profile    | Compose Override       | ASR | TTS       |
| ---------- | ---------------------- | --- | --------- |
| `cpu`      | `compose.cpu.yml`      | CPU | CPU, FP16 |
| `gpu`      | `compose.gpu.yml`      | GPU | GPU, FP16 |
| `npu`      | `compose.npu.yml`      | NPU | GPU, FP16 |
| `gpu-wsl`  | `compose.gpu-wsl.yml`  | GPU | CPU, FP16 |

The GPU override gives both services `/dev/dri` and the host's numeric
`RENDER_GROUP_ID` as a supplementary group. The NPU override gives
audio-analyzer `/dev/dri`, `/dev/accel`, the `RENDER_GROUP_ID` group, and
`ZE_ENABLE_ALT_DRIVERS=libze_intel_npu.so`, while text-to-speech gets
`/dev/dri` and `RENDER_GROUP_ID` for GPU inference.
The host must have the corresponding device nodes and compatible drivers;
the images must include the required OpenVINO runtimes. No privileged mode or
extra Linux capabilities are enabled.

The `gpu-wsl` override gives the ASR service `/dev/dxg` and a read-only
`/usr/lib/wsl` library mount. It does not require `/dev/dri` or `RENDER_GROUP_ID`.
Use this profile inside WSL 2, not the native `gpu` override. ASR uses the iGPU,
while SpeechT5 TTS uses CPU with its own FP16 model and does not need GPU device
mapping. Docker Compose 2.24.4 or newer is required
for the WSL override files.

`setup_env.sh` detects `RENDER_GROUP_ID` for Make. When invoking Compose
directly, set it to the host render group's numeric ID. The NPU override does
not add a separate group for `/dev/accel`; the NPU device nodes must belong to
the render group or otherwise be accessible to the container user (UID 1000).
Inspect their group with `stat -c '%g' /dev/accel/accel0`.

Direct GPU startup:

```bash
export RENDER_GROUP_ID=$(getent group render | cut -d: -f3)
COMPOSE_PROFILES=gpu docker compose -f compose.yml -f compose.gpu.yml \
  up -d --no-build
```

Direct WSL iGPU startup:

```bash
COMPOSE_PROFILES=gpu-wsl docker compose -f compose.yml -f compose.gpu-wsl.yml \
  up -d --no-build
```

Direct NPU startup (use the NPU voice override instead of the GPU override):

```bash
export RENDER_GROUP_ID=$(getent group render | cut -d: -f3)
COMPOSE_PROFILES=npu docker compose -f compose.yml -f compose.npu.yml \
  up -d --no-build
```

Export `VOICE_ASR_DEVICE` (`CPU`, `GPU`, or `NPU`) to set default ASR inference.
The native GPU and NPU voice overrides also accept `VOICE_TTS_DEVICE` (`CPU` or
`GPU`) and `VOICE_TTS_DTYPE`, which defaults to `fp16`. The CPU and `gpu-wsl`
profiles use CPU/FP16 for TTS.
Device selection alone does not expose hardware: keep the
corresponding Compose overrides. Each Audio pipeline run sends its variant's
device, but it cannot add a missing container device mapping. SpeechT5 does not document NPU support, so the
NPU profile defaults to GPU for TTS. For CPU inference on a native GPU or NPU
host, export `VOICE_ASR_DEVICE=CPU VOICE_TTS_DEVICE=CPU VOICE_TTS_DTYPE=fp16`.
Run `make run`
to regenerate the detected profile and recreate affected containers without
deleting the named model or cache volumes. For manual Compose commands, update
both the profile and override filenames. Do not edit the generated `.env` file.
GPU utilization metrics may be unavailable under WSL even when inference works;
the native Linux GPU collectors depend on driver interfaces not exposed by WSL.

Diarization and sentiment analysis are disabled. TTS supports English in this
configuration. Changing a language label alone does not add multilingual
synthesis support.

Installing catalog models from the Models page requires network access from
model-download to Hugging Face. The first start of each Voice service requires
network access from that service to Hugging Face. Later starts reuse the named
model and cache volumes. Configure `http_proxy`, `https_proxy`, and `no_proxy`
as required. Do not pass tokens through Docker build arguments.

To stop only the optional services, preserving their caches:

```bash
COMPOSE_PROFILES=cpu docker compose -f compose.yml -f compose.cpu.yml stop \
  audio-analyzer text-to-speech
```

For GPU/NPU/WSL, use the same profile and override files as at startup.

## Browser and Input Requirements

- Microphone capture requires HTTPS or `localhost`, permission to use the
  microphone, and browser support for MediaRecorder and Web Audio.
- Recording stops automatically after 60 seconds and is converted in the
  browser to mono PCM 16-bit WAV at 16 kHz. Audio Analyzer validates uploaded
  files according to its runtime format and size configuration; a file it
  rejects ends the job as `FAILED` with the generic error text.
- Select a recognition language for STT. Default: English.
- TTS input must contain 1-200 characters after trimming whitespace.
- Playback is explicit using the audio controls. Generated WAV can be downloaded.
- The STT page walks through three steps: **1. Select input** (available audio
  samples, file upload, or microphone recording, in that order; samples are
  selected by default), **2. Verify audio (optional)** (a waveform preview and
  player for the selected audio), and **3. Select language**, then press
  **Transcribe**. All three inputs are shown stacked; the selected one is
  highlighted. Available audio samples come from `GET /api/v1/voice/recordings`.
  The transcription appears below the controls.
- The TTS **Voice** menu initially selects `Ryan`. It also offers `Miles`,
  `Aaron`, `Nora`, `Elena`, `Kabir`, and `Angus`. Changing the voice preserves
  the text and clears the previous generated audio, metrics, and error.
- Audio previews display a waveform sampled from the actual decoded audio,
  using browser Web Audio and the existing Recharts library. No audio is sent
  to an additional visualization service. Waveforms are approximate amplitude
  overviews, not interactive seek controls; use the native audio player to seek.
  The vertical scale adapts to each clip's sampled peak, filling about 90% of
  the plot height while preserving relative amplitudes. Silence stays flat.
  This is display-only scaling: playback volume and downloaded audio are unchanged.
  Waveform heights do not indicate absolute loudness across different clips.
  If visualization fails, playback and WAV download remain available.
- Audio uses the existing semantic color tokens, typography, shadcn controls
  and metrics components in both light and dark themes. It is accessed from
  **Pipelines**, not a separate navigation item. No model or synthesis-rate
  selectors are added; those settings
  remain service configuration. Upload format support follows the Audio
  Analyzer configuration.
- After ViPPET accepts a managed run and returns a valid job ID, the UI shows
  **Audio pipeline run started**. It shows **Audio pipeline run completed** only
  after applying the transcript or downloading and applying the generated WAV.
  A failed run keeps its inline error and shows a persistent, dismissible
  **Audio pipeline run failed** notification. A job stopped by the user
  shows **Audio pipeline run cancelled** instead.
- While a managed run is in progress, **Transcribe** and **Generate speech**
  become a **Stop** button, like the Vision pipeline Run/Stop button. Stop
  cancels the backend job (`DELETE /api/v1/jobs/audio/{job_id}`) and the UI shows
  **Audio pipeline run cancelled** once the job reports `COMPLETED` without a
  transcript or artifact. If the job
  has not been accepted yet, Stop aborts the pending request. The microphone
  **Cancel** button only stops local recording. Replaced requests and unmount
  cleanup discard stale terminal responses without showing lifecycle
  notifications.

## API

Voice runs are managed pipeline jobs: run endpoints return `202` and create
tracked process-local Audio jobs.

### Managed pipeline runs

The preset API follows the asynchronous ViPPET job pattern:

- `GET /api/v1/voice/pipelines` lists the Audio preset catalog.
- `GET /api/v1/voice/recordings` lists the predefined recordings (filename,
  duration in seconds, and audio URL) registered from the recordings manifest.
- `GET /api/v1/voice/recordings/{filename}/audio` returns one registered
  recording as `audio/wav` for preview. Unregistered names return `404`.
- `POST /api/v1/voice/pipelines/{pipeline_id}/variants/{variant_id}/runs`
  returns `202` with a job ID for the selected device variant.

Managed Speech to Text runs accept a JSON body with a registered `recording`
filename and a two-letter `language`, or multipart `file` and `language` fields
for uploaded or recorded input.
ViPPET copies multipart input to a random private temporary path
owned by the job and removes it after every terminal outcome or shutdown.
Managed Text to Speech runs require both `input` and `voice`:

```json
{"input": "Custom text up to 200 characters", "voice": "Miles"}
```

The TTS body rejects unknown fields, unsupported voices, blank input, and input
longer than 200 characters. Sending this body to an STT pipeline returns 400.
A request without a body returns 415. YAML `defaults` only prefill the UI form.
Job state is process-local and is lost when the ViPPET backend restarts. TTS
artifacts remain on the mounted Audio output directory until deployment cleanup
removes them.

### Audio job status and artifacts

- `GET /api/v1/jobs/audio/status` lists Audio job operational metadata without
  transcript content, Text to Speech input text, uploaded filenames, or local
  paths. Jobs are ordered oldest first, matching the Vision job list.
- `GET /api/v1/jobs/audio/{job_id}/status` returns `state` (`RUNNING`,
  `COMPLETED`, or `FAILED`), selected variant metadata,
  and, when available, the transcript or the public WAV `artifact_url`. A job
  stopped before it produced a result is `COMPLETED` without either.
- `GET /api/v1/voice/jobs/{job_id}/artifact` returns a completed TTS WAV.
- `DELETE /api/v1/jobs/audio/{job_id}` stops a `RUNNING` job: `200`
  when cancellation was requested, `404` for an unknown job, and `409` when the
  job has already finished.

### Headless managed pipeline examples

Headless clients use the same managed API as the browser. The examples below
assume Nginx is available at `http://127.0.0.1` and bypass environment proxies
for local traffic.

List the Audio catalog:

```bash
curl --noproxy '*' -sS http://127.0.0.1/api/v1/voice/pipelines
```

Start managed CPU STT with a predefined recording, after listing them:

```bash
curl --noproxy '*' -sS http://127.0.0.1/api/v1/voice/recordings
curl --noproxy '*' -sS -X POST \
  -H 'Content-Type: application/json' \
  -d '{"recording": "sample_female.wav", "language": "de"}' \
  http://127.0.0.1/api/v1/voice/pipelines/speech-to-text/variants/cpu/runs
```

Start managed NPU STT with an uploaded recording and Polish recognition:

```bash
curl --noproxy '*' -sS -X POST \
  -F 'file=@recording.wav;type=audio/wav' \
  -F 'language=pl' \
  http://127.0.0.1/api/v1/voice/pipelines/speech-to-text/variants/npu/runs
```

Start managed CPU TTS with request-specific text and voice:

```bash
curl --noproxy '*' -sS -X POST \
  -H 'Content-Type: application/json' \
  -d '{"input":"Headless Audio pipeline check.","voice":"Ryan"}' \
  http://127.0.0.1/api/v1/voice/pipelines/text-to-speech/variants/cpu/runs
```

Each start returns HTTP 202 with a `job_id`. Poll the job until its `state` is
`COMPLETED` or `FAILED`. The run also appears under
**Jobs > Audio**:

```bash
curl --noproxy '*' -sS \
  http://127.0.0.1/api/v1/jobs/audio/<job_id>/status
```

A completed STT job contains `transcript`. A completed TTS job contains
`artifact_url`; download that managed WAV through ViPPET:

```bash
curl --noproxy '*' -sS -o speech.wav \
  http://127.0.0.1/api/v1/voice/jobs/<job_id>/artifact
```

A backend restart discards job lookup state, so
even a persisted TTS WAV is no longer retrievable through the job endpoint
after that restart.

Backend service locations are configured with `AUDIO_ANALYZER_URL` (default
`http://audio-analyzer:8010`) and `TEXT_TO_SPEECH_URL` (default
`http://text-to-speech:8011`). They must be deployment-controlled URLs, never
user-provided targets. Internal service calls bypass environment HTTP proxies.

The run endpoint validates the request and returns `202` immediately; it does
not wait for the speech service. Errors detected before the job starts are
returned as HTTP status codes: `400` when the body does not match the pipeline
operation, `404` for an unknown pipeline, variant, or recording, `409` when the
pipeline is unavailable, `413` for oversized uploads, `415` for an unsupported
content type, and `422` for invalid request fields.

Uploads are limited to 200 MiB. Nginx enforces `client_max_body_size 200m` on
the whole multipart request and usually rejects an oversized upload first, with
its own HTML `413` response. The backend enforces the same limit on the file
content while staging it to disk (`MAX_STT_UPLOAD_BYTES`) and returns a JSON
`413`. Keep the two values in sync.

Speech service calls run inside the background job. The adapter uses a
5-second connection timeout and a 20-minute total upstream deadline, and limits
responses to 128 KiB for STT and 64 MiB for TTS. Any upstream failure, including
a rejected input, a busy or unavailable service, a timeout, or an invalid
response, ends the job as `FAILED` with the fixed error text
`Audio pipeline execution failed.`. The upstream reason is written only to the
ViPPET backend log; it is not returned to the client.

The browser stops waiting for a run 1210 seconds after it starts, including
polling, and shows `Conversion timed out.`. This does not cancel the backend
job, which keeps running and can still complete; use **Stop** to cancel it.
The Nginx Voice read and send timeouts are also 1210 seconds, but they apply
only to the individual start, status, and artifact requests, which do not wait
for the conversion. Nginx disables response caching for Voice routes.

## Metrics

Each successful conversion displays its own timing cards, reusing the existing
ViPPET metrics UI. The route renders either the STT or TTS result and metrics;
there are no operation tabs.

| Metric             | Unit | Measurement interval                                                                                   |
| ------------------ | ---- | ------------------------------------------------------------------------------------------------------ |
| Request duration   | ms   | Browser first-fetch start through a completed managed job status.                                      |
| Service round trip | ms   | ViPPET upstream POST start through receipt and validation of the complete service response body.       |

Both intervals use monotonic clocks. Managed request duration includes the
initial POST and job polling, but excludes the later TTS artifact download.
Both exclude microphone recording, WAV
preparation and playback. Service round trip includes connection setup,
transport, service queueing and processing. Neither is a pure model inference
measurement or time to first byte/token. Startup/model loading can increase the
observed duration. The values are not aggregated benchmarks.

Completed managed jobs expose the service round trip in
`service_round_trip_ms`. Failures do not include this success metric. No
`/v1/performance` polling is used: the services' global `last_ms` cannot reliably
identify a particular request.

The previous result and its timings are cleared when the input or recognition
language changes, a new recording starts, or a replacement conversion starts.
Failed or cancelled browser requests do not display new results or timings.
Navigating away aborts browser recording, polling, or managed-run fetches. It does
not cancel an already-started managed backend job, which can still finish and
persist a TTS artifact; use **Stop** to cancel the job. Missing or invalid service timing values show "Service
round trip unavailable" while conversion and browser-side duration remain
available.

Expand **Platform metrics (system-wide)** to use the existing live metrics
dashboard for CPU, memory, GPU and available NPU telemetry. Video FPS and pipeline
latency are hidden in Voice. These charts represent the whole platform, including
other workloads, not isolated STT/TTS utilization or a snapshot of the conversion.
They use the existing metrics-manager stream and do not start extra service polls.

## Storage and Security

ViPPET does not log recording contents, sentences, or transcripts. It copies
each manifest-registered local WAV into `shared/audio/input/auto` after
validating its logical filename and WAV structure, and atomically publishes it.
Audio presets cannot select arbitrary
paths or URLs. Completed preset TTS files are atomically written under
`shared/audio/output` with UUID filenames and served only for known completed
jobs. Define deployment cleanup for these files.

`make clean-output-audio` removes generated files under `shared/audio/output`.
`make clean` also removes those files and the whole `shared/audio/input` tree;
see [Deployment](#deployment) for everything else it removes. Job metadata
and STT transcripts are process-local. A backend restart leaves completed WAV
files on disk but removes the job lookup required by the artifact endpoint.

Both direct adapter responses use `Cache-Control: no-store`. The upstream TTS
service has output persistence disabled. Audio-analyzer still writes recordings/transcripts into its
dedicated `voice_asr_storage` volume, clears storage on service startup, and
deletes chunks after successful processing. Its exit-time chunks sweep is
disabled because the chunks path is a volume mount, so interrupted runs can
leave files in `voice_asr_chunks`. There is no automatic per-request retention
deadline. This is not a zero-retention deployment; arrange storage cleanup
according to your data policy before using sensitive recordings. Removing
model/cache volumes is not necessary to clear session data.

Deployment owners must provide HTTPS, access control, request-rate limits, and
appropriate retention. The published audio ports expose upstream APIs directly,
bypassing ViPPET's proxy validation and limits. The base Compose mappings are
not restricted to loopback; use host firewall rules or a deployment override,
and protect reachable endpoints with appropriate access control and TLS.

## Known limitations

- **Voice models are downloaded twice.** The catalog install downloads PyTorch
  checkpoints (about 0.9 GB) that the Voice services never read, while the
  services download and export their own models; see
  [Model provisioning](#model-provisioning).
- **Installed does not reflect what runs.** The Run button is enabled by the
  catalog checkpoints, not by the models the services load. A pipeline can be
  runnable while its service is still downloading or has failed to provision
  its model; the job then ends as `FAILED`.
- **First start needs Hugging Face access.** Each Voice service downloads its
  model on first start, so its container needs network access to Hugging Face,
  through a proxy if required.
- **No offline pre-provisioning.** Pre-provisioning the Voice models for
  offline hosts, for example by installing them from the **Models** page, is
  not supported in this release.

A single model-provisioning path is tracked as technical debt in ITEP-98337,
recorded when
[PR #3248](https://github.com/open-edge-platform/edge-ai-libraries/pull/3248)
was merged.

## Verification

```bash
PYTHONPATH=vippet .venv/bin/python -m unittest discover \
  -s vippet/tests/unit/api_tests -p voice_test.py -v
```
