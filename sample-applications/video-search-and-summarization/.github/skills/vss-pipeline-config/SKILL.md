---
name: vss-pipeline-config
description: Use this skill for the video-search-and-summarization sample app whenever a developer wants to tune the summarization pipeline, improve summary quality, or diagnose why a video is too slow to process. Trigger especially for requests to change frames per chunk, adjust chunk duration, turn audio transcript on/off, tune frame sampling or multi-frame settings, or explain latency/compute/quality trade-offs in VSS.
---

# VSS pipeline configuration knobs

Use this skill when helping developers tune the Video Search & Summarization (VSS) sample application's summarization pipeline. Ground every answer in the current repository: if code changed, re-open the cited files before giving final guidance. For a full tabular reference, read `references/parameter-reference.md`.

## Environment setup (run first)

This skill drives the Video Search & Summarization app through its real source
files, so the VSS application must be present and you must run commands from its
app root. **Do this before anything else**, and it works whether or not the VSS
source is already in your workspace.

Run the bundled bootstrap. It first tries to find an existing VSS checkout -
walking up from the current directory and inspecting the enclosing git repo - and
reuses it **without ever re-cloning**. Only when no checkout is found does it do a
shallow, single-branch, sparse checkout of just
`sample-applications/video-search-and-summarization` from `main`. It prints the
resolved app root on stdout:

```bash
# SKILL_DIR is THIS skill's own directory (shown to you when the skill loads);
# in-repo it is .github/skills/vss-pipeline-config. Works the same if the skill is installed standalone.
SKILL_DIR=".github/skills/vss-pipeline-config"
APP_ROOT="$(bash "$SKILL_DIR/scripts/vss-bootstrap.sh")"
cd "$APP_ROOT"
```

Every command below assumes the working directory is this `APP_ROOT`. To pull
from a fork/branch or reuse a specific checkout dir, override `VSS_REPO_URL`,
`VSS_REPO_BRANCH`, or `VSS_CLONE_DIR` before running it.

## Mental model

The summarization path is:

1. UI builds `SummaryPipelineDTO` and POSTs it to `POST /summary`.
2. Pipeline manager stores `reqBody.sampling` as `state.userInputs` and validates/derives `state.systemConfig`.
3. EVAM/video ingestion receives `parameters.frame = samplingFrame` and `parameters.chunk_duration = chunkDuration`.
4. `ChunkingService` groups returned frames into VLM captioning calls using `samplingFrame`, `frameOverlap`, and `multiFrame`.
5. Optional audio transcription adds time-matched transcript snippets to chunk VLM prompts; optional full-transcript summary adds a condensed audio summary to the final LLM map-reduce prompt.

Key code paths:
- API DTO: `pipeline-manager/src/summary/models/summary-pipeline.model.ts`
- API validation/default merge: `pipeline-manager/src/summary/controllers/summary.controller.ts`
- Server defaults/env: `pipeline-manager/src/config/configuration.ts`, `pipeline-manager/src/video-upload/services/app-config.service.ts`
- EVAM request: `pipeline-manager/src/evam/services/evam.service.ts`
- VLM batching/audio transcript use: `pipeline-manager/src/state-manager/queues/chunking.service.ts`
- Audio/full transcript summary: `pipeline-manager/src/state-manager/queues/audio-queue.service.ts`, `pipeline-manager/src/state-manager/queues/summary-queue.service.ts`
- UI fields: `ui/react/src/components/VideoActions/VideoSummarizeFlow.tsx` and legacy drawer `ui/react/src/components/Drawer/VideoUpload.tsx`

## Core knobs

### Chunk duration

- **User-facing name:** `chunk Duration (secs)` in the UI.
- **API field:** `sampling.chunkDuration` in `SummaryPipelineDTO`.
- **Where to set:** UI `NumberInput id='chunkDuration'`; direct API request body; CLI YAML may use `chunkDuration`.
- **Default:** UI initializes to `8`; API requires the field and does not add an API default.
- **Range in code:** UI minimum is `2`; no explicit backend maximum. Use practical values based on content: short events ~5-15s, long lectures/presentations ~30-60s.
- **What it does:** Sent to EVAM as `parameters.chunk_duration`; also maps frame IDs back to transcript/search time windows.
- **Trade-off:** Shorter chunks improve temporal precision and reduce the amount of unrelated context per caption, but create more chunks and more downstream work. Longer chunks reduce orchestration overhead, but each caption covers a broader time span, so brief events and transcript alignment can be diluted.

### Frames per chunk / frame sampling

- **User-facing name:** `Frame per chunk`.
- **API field:** `sampling.samplingFrame`.
- **Where to set:** UI `NumberInput id='sampleFrame'`; direct API request body; CLI YAML may use `samplingFrame`.
- **Default:** UI initializes to `8`; API requires the field.
- **Range in code:** UI minimum is `2`. Backend requires `samplingFrame + frameOverlap == sampling.multiFrame` and that the derived multi-frame value does not exceed the configured maximum batch size.
- **What it does:** Sent to EVAM as `parameters.frame`; used by `ChunkingService` as the number of frames per chunk when grouping frames and aligning audio transcript snippets.
- **Trade-off:** More sampled frames give the VLM more visual evidence and improve chances of capturing short actions. Cost grows roughly with the number of images captioned: more frames increase ingestion output, VLM payload size, queue pressure, and latency.

### Frame overlap

- **User-facing name:** `Frames Overlap` in Advanced/Ingestion Settings.
- **API field:** `sampling.frameOverlap`.
- **Where to set:** UI `NumberInput id='overrideMultiFrame'` despite the misleading id; direct API request body.
- **Default:** `0` from UI state and server config.
- **Range in code:** UI min `0`, max `systemConfig.multiFrame`; effective safe range is `0..(systemConfig.multiFrame - samplingFrame)` because the backend rejects mismatches/oversized batches.
- **What it does:** `ChunkingService` uses it to slide VLM frame windows: `windowLength = multiFrame - frameOverlap`; overlapping frames are repeated across adjacent VLM captioning calls.
- **Trade-off:** Overlap reduces boundary misses when an event spans two frame groups. It also duplicates frames in VLM calls, so latency and token/image cost increase.

### Multi-frame factor / batch size

- **User-facing name:** `Batch size` / `Multi Frames`.
- **API field:** `sampling.multiFrame`.
- **Where to set:** Usually not typed directly; UI displays a read-only value computed as `sampleFrame + frameOverlap`. The maximum comes from pipeline-manager env `MULTI_FRAME_COUNT`, passed from compose variable `PM_MULTI_FRAME_COUNT` or Helm `pipelinemanager.env.MULTI_FRAME_COUNT`.
- **Default:** server max is `MULTI_FRAME_COUNT ?? 12`; `setup.sh` defaults `PM_MULTI_FRAME_COUNT=12`. Helm values also default to `12`, with some OVMS accelerator paths overriding to `6`.
- **Range in code:** request value must be `<= systemConfig.multiFrame` and exactly equal to `frameOverlap + samplingFrame`; otherwise `POST /summary` returns `BadRequestException`.
- **What it does:** Caps how many images are sent to one VLM captioning request. `ChunkingService` slices frames into groups up to this size.
- **Trade-off:** Larger batches give the VLM broader temporal context per caption and can reduce the number of captioning calls when overlap is used. They also create heavier multimodal requests and may exceed model/backend limits; smaller batches are safer and lower per-call latency but provide less cross-frame context.

### Audio transcription on/off

- **User-facing names:** `Use Audio Transcription`, `Audio Models`, and `Summarize audio transcript for final summary`.
- **API fields:** include `audio.audioModel` to enable transcription; set `audio.useFullTranscriptSummary` to control whether the complete transcript is summarized and injected into the final video summary.
- **Where to set:** UI Audio Settings checkboxes/select; direct API `audio` object; default for full-transcript summarization via env `AUDIO_USE_FULL_TRANSCRIPT_SUMMARY` (`PM_AUDIO_USE_FULL_TRANSCRIPT_SUMMARY` in compose/setup, `pipelinemanager.env.AUDIO_USE_FULL_TRANSCRIPT_SUMMARY` in Helm).
- **Defaults:** UI `audio` state starts `true` if audio models are available; selected model defaults to `systemConfig.meta.defaultAudioModel`. `useFullTranscriptSummary` default comes from `AUDIO_USE_FULL_TRANSCRIPT_SUMMARY ?? 'true'`. `produceFinalSummary=false` forces UI to send `useFullTranscriptSummary: false`.
- **Range:** booleans for the toggles; `audioModel` must be one of the audio service models returned through `GET /app/config` metadata.
- **What it does:** If `audioModel` is present, `PipelineService` emits `AUDIO_TRIGGERED`, `AudioQueueService` posts a Whisper transcription request, and `ChunkingService` injects time-matched transcript snippets into frame caption prompts. If `useFullTranscriptSummary` is true, `SummaryQueueService` first summarizes the complete transcript and injects it through `%audio_summary%` in the final summary prompt.
- **Trade-off:** Audio improves quality for narrated/dialogue-heavy videos and helps explain visual ambiguity. It adds Whisper latency plus, when full-transcript summary is enabled, an extra LLM map-reduce pass before the final video summary.

## How to answer tuning questions

1. Identify whether the developer is using the UI, REST API, compose/setup, Helm, or CLI.
2. Name the exact field/env var they should change and where it is consumed.
3. Explain the expected direction of impact:
   - Faster/lower cost: increase `chunkDuration`, decrease `samplingFrame`, keep `frameOverlap=0`, lower `PM_MULTI_FRAME_COUNT` if backend struggles, disable audio/full transcript summary when audio is irrelevant.
   - Better quality: decrease `chunkDuration` for short events, increase `samplingFrame`, add small `frameOverlap`, enable audio for speech-heavy videos, keep final summary enabled.
4. Warn about the hard backend invariant: `sampling.multiFrame` must equal `sampling.frameOverlap + sampling.samplingFrame` and must not exceed the configured maximum `MULTI_FRAME_COUNT`.
5. For exact defaults/ranges, cite `references/parameter-reference.md` and the source files above.
