<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Audio Pipeline Architecture: STT, TTS and Metrics

These diagrams describe the implemented Audio integration as of 2026-11-19.
They follow the [C4 model](https://c4model.com/diagrams) at System Context,
Container and Component levels only. Flow diagrams describe runtime behavior;
there is no Code-level diagram.

## Scope and Notation

- The system of interest is ViPPET. Browser operators and headless automation
  use its public API. Audio Analyzer, Text to Speech, Model
  Download and Metrics Manager are independently deployable supporting software
  systems, even when installed in the same Docker Compose stack.
- A C4 container is an application or data store, not necessarily a Docker
  container. The browser SPA and its Nginx web server are separate C4 containers;
  Nginx serves the SPA from the `vippet-ui` Docker image.
- Each Component view zooms into one ViPPET container. Components describe
  existing responsibilities, not proposed services or new source files.
- Relationships in C4 diagrams describe dependencies/calls; response data is
  summarized in their labels. Flow diagrams show response direction explicitly.
- C4 notation is rendered using Mermaid `flowchart`: every box identifies its
  type, technology where relevant, and responsibility. Blue boxes belong to
  ViPPET; gray boxes are dependencies outside the view's system/container boundary.
  Runtime diagrams use `sequenceDiagram` and `flowchart`. This avoids the
  overlapping labels of Mermaid's experimental native C4 layout.
- Unrelated video pipelines, LLMs, chat history and kiosk-core are out of scope.
  STT and TTS are independent conversions, not an automatic chained conversation.

## C4 Level 1: System Context

```mermaid
flowchart TB
  operator["Operator<br/>[Person]<br/>Runs Audio pipelines in the browser"]:::person
  automation["Automation client<br/>[External software system]<br/>Runs Audio pipelines headlessly"]:::external
  vippet["ViPPET<br/>[Software system]<br/>Audio catalog, jobs and metrics"]:::internal
  asr["Audio Analyzer<br/>[External software system]<br/>Transcribes recordings"]:::external
  tts["Text to Speech<br/>[External software system]<br/>Synthesizes speech"]:::external
  models["Model Download<br/>[External software system]<br/>Downloads catalog checkpoints"]:::external
  telemetry["Metrics Manager<br/>[External software system]<br/>Collects platform telemetry"]:::external
  hub["Hugging Face Hub<br/>[External software system]<br/>Hosts Whisper Base and SpeechT5"]:::external
  operator -->|Uses web UI| vippet
  automation -->|Uses public Audio HTTP API| vippet
  vippet -->|Recording to transcript| asr
  vippet -->|Text to audio| tts
  vippet -->|Requests catalog model installation| models
  vippet -->|Subscribes to platform metrics| telemetry
  asr -->|Downloads its own model on first start| hub
  tts -->|Downloads its own model on first start| hub
  models -->|Downloads PyTorch checkpoints| hub
  classDef person fill:#08427b,color:#fff,stroke:#052e56
  classDef internal fill:#1168bd,color:#fff,stroke:#0b4884
  classDef external fill:#666,color:#fff,stroke:#444
```

The operator uses the ViPPET UI, while automation uses the same ViPPET Audio API
without a browser. Direct upstream API access is possible through published
service ports, but bypasses the ViPPET proxy and its controls. Audio Analyzer
and Text to Speech provision their own models; the Model Download path only
fills the ViPPET catalog (see [Flow: Voice Model Provisioning](#flow-voice-model-provisioning)).

## C4 Level 2: Containers

```mermaid
flowchart TB
  operator["Operator<br/>[Person]"]:::person
  automation["Automation client<br/>[External software system]"]:::external
  subgraph vippet[ViPPET - System]
    direction TB
    spa["Browser UI<br/>[Container: React / TypeScript]<br/>Audio catalog, execution, Jobs, notifications, model installation and metrics"]:::internal
    web["UI web server<br/>[Container: Nginx :80]<br/>Serves assets and proxies API / SSE"]:::internal
    api["Backend<br/>[Container: FastAPI / Python :7860]<br/>Catalog, process-local jobs and artifacts"]:::internal
    spa -->|"Assets, API requests and SSE<br/>HTTP; HTTPS at deployment edge"| web
    web -->|"/api/v1/voice/*, /api/v1/jobs/audio/* and model APIs<br/>HTTP :7860"| api
  end
  asr["Audio Analyzer<br/>[External software system]<br/>Whisper Base / OpenVINO"]:::external
  tts["Text to Speech<br/>[External software system]<br/>SpeechT5 / OpenVINO"]:::external
  asrmodels[("voice_asr_models<br/>[External data store: named volume]<br/>Audio Analyzer OpenVINO models")]:::external
  ttsmodels[("voice_tts_models<br/>[External data store: named volume]<br/>Text to Speech OpenVINO models")]:::external
  hub["Hugging Face Hub<br/>[External software system]<br/>Model source"]:::external
  downloader["Model Download<br/>[External software system :8000]<br/>Catalog download jobs"]:::external
  modelstore[("Shared model storage<br/>[External data store]<br/>shared/models/output")]:::external
  audiostore[("Managed Audio storage<br/>[External data store]<br/>shared/audio input and output")]:::external
  telemetry["Metrics Manager<br/>[External software system]<br/>SSE, Telegraf and hardware collectors"]:::external
  operator -->|Browser interaction| spa
  automation -->|"Catalog and managed jobs<br/>HTTP JSON / multipart"| web
  api -->|"POST /v1/audio/transcriptions<br/>HTTP multipart :8010; JSON response"| asr
  api -->|"POST /v1/audio/speech<br/>HTTP JSON :8011; WAV response"| tts
  api -->|"Start and poll catalog model jobs<br/>HTTP JSON :8000"| downloader
  api -->|"Checks catalog checkpoint exists<br/>(sets Installed)"| modelstore
  api -->|"Reads registered STT input; atomically writes and serves TTS WAV"| audiostore
  downloader -->|"Downloads PyTorch checkpoints"| hub
  downloader -->|"Writes PyTorch checkpoints<br/>(not read by Voice services)"| modelstore
  asr -->|"Downloads Whisper Base on first start"| hub
  asr -->|"Exports, stores and loads OpenVINO model"| asrmodels
  tts -->|"Downloads SpeechT5 on first start"| hub
  tts -->|"Exports, stores and loads OpenVINO model"| ttsmodels
  web -->|"GET /metrics/stream<br/>HTTP / SSE :9090"| telemetry
  classDef person fill:#08427b,color:#fff,stroke:#052e56
  classDef internal fill:#1168bd,color:#fff,stroke:#0b4884
  classDef external fill:#666,color:#fff,stroke:#444
```

Nginx streams Voice request bodies and disables response caching. The backend
stages each upload to a private temporary file, and the background job then
streams that file to Audio Analyzer, which owns input validation. Upload limits
are described in [Flow: Managed Speech to Text](#flow-managed-speech-to-text).
The backend retains response-size and deadline limits. Upstream failures end the
job as `FAILED` with a fixed error text; upstream details are only logged.
Environment HTTP proxy settings are not used for these calls.

### Deployment and Storage Boundaries

- The current Compose file publishes `8010:8010` and `8011:8011` without a
  loopback host address. Network reachability depends on the host/firewall;
  these bindings are not restricted to localhost by this configuration.
  Protect direct access with deployment-level access control and TLS.
- Audio Analyzer and Text to Speech provision their own models. On first
  start, each downloads its configured model from Hugging Face, exports it to
  OpenVINO (Whisper Base with `int8` weights, SpeechT5 with `fp16`) and stores
  it in its own named volume, `voice_asr_models` or `voice_tts_models`. Later
  starts reuse the volume. Each service compiles the model for the configured
  or per-request device when it loads it. Neither service mounts
  `shared/models`. A first start needs Hugging Face access from the service
  container; until provisioning completes, the service is not healthy (the
  Compose health checks allow a 15-minute start period).
- The Models page starts ViPPET background jobs for the `voice-whisper-base`
  and `voice-speecht5` catalog entries. `ModelManager` forwards their Hugging
  Face requests to Model Download with `download_path="."`, polls the returned
  job, and marks a model Installed when its PyTorch checkpoint exists under
  `shared/models/output/huggingface`. The Audio pipeline `required_models`
  gate uses this state. The Voice services never read these checkpoints; see
  [Known limitations](../user-guide/voice-conversion.md#known-limitations).
- ASR keeps runtime cache, chunks and storage in `voice_asr_cache`,
  `voice_asr_chunks` and `voice_asr_storage`. Recordings/transcripts can persist
  in its storage volume; clear-on-startup is enabled, not a per-request retention
  guarantee. Exit-time chunk cleanup is disabled because the chunks path is a
  volume mount; failed or interrupted runs can therefore leave chunks behind.
  TTS keeps runtime cache and storage in `voice_tts_cache` and
  `voice_tts_storage`, but `PERSIST_OUTPUTS=false` disables output persistence.
- ViPPET stores the registered STT recordings and every completed managed TTS
  job artifact in the mounted `shared/audio` tree. TTS runs use UUID-named files
  under `shared/audio/output`. Audio job metadata
  and STT transcripts are process-local. Uploaded or recorded managed STT input
  is copied to a UUID-named file in a private manager-owned temporary directory
  and removed after success, failure, cancellation, registration failure, or
  shutdown. `make clean` removes generated TTS artifacts and the whole
  `shared/audio/input` tree, but not named volumes; see the
  [user guide](../user-guide/voice-conversion.md#deployment) for everything it
  removes. Browser results and per-conversion timings remain
  in React state; blob URLs are revoked during cleanup.
- Clients use the ViPPET API through Nginx. Run requests return `202`, then
  clients poll process-local job state.
- Hardware overrides determine the default service devices and which device
  nodes are mounted. Each Audio variant selects among compatible,
  visible devices. Telemetry reflects the whole host and can include unrelated
  workloads on those devices.

## C4 Level 3: Browser UI Components

```mermaid
flowchart TB
  web["UI web server<br/>[Container: Nginx]<br/>Voice API and SSE proxy"]:::external
  subgraph spa[Browser UI - Container]
    direction TB
    catalog["PipelineCards<br/>[Component: React]<br/>Shared cards in the Audio tab of Pipelines"]:::internal
    voice["VoiceConversion<br/>[Component: React]<br/>Route-selected STT or TTS workflow"]:::internal
    variant["PipelineVariantSelect<br/>[Component: React]<br/>Route-backed Audio device variant selection"]:::internal
    recorder["Recording adapter<br/>[Component: Web Audio]<br/>captureWav prepares local PCM WAV"]:::internal
    audio["VoiceAudio<br/>[Component: Web Audio / Recharts]<br/>Waveform and native audio playback"]:::internal
    timings["VoiceMetrics<br/>[Component: React]<br/>Request and service round-trip timings"]:::internal
    jobs["Jobs / Audio tab<br/>[Component: React / RTK Query]<br/>Oldest-first Audio job list polled every 2 seconds"]:::internal
    detail["AudioJobDetail<br/>[Component: React / RTK Query]<br/>Polls status and displays transcript or WAV link"]:::internal
    notifications["Toaster / shared toast<br/>[Component: Sonner]<br/>Audio run lifecycle notifications"]:::internal
    stream["MetricsProvider / useMetricsStream<br/>[Component: EventSource]<br/>Shared SSE subscription and reconnect"]:::internal
    store["Metrics state<br/>[Component: Redux Toolkit]<br/>Current samples and connection state"]:::internal
    dashboard["MetricsDashboard<br/>[Component: React / Recharts]<br/>useMetrics and useMetricHistory"]:::internal
    cards["MetricCard<br/>[Component: React]<br/>Shared numeric presentation"]:::internal
    voice -->|"Uploaded or recorded STT<br/>Async capture and AbortSignal"| recorder
    voice -->|Renders selected route variant| variant
    variant -->|Updates route parameters| voice
    voice -->|Blob URL props| audio
    voice -->|Timing props| timings
    voice -->|Lifecycle events| notifications
    voice -->|Always mounts below VoiceMetrics in right rail; no video metrics| dashboard
    jobs -->|Opens selected Audio job| detail
    stream -->|Dispatches Redux actions| store
    dashboard -->|Reads Redux selectors| store
    dashboard -->|Renders platform values| cards
  end
  catalog -->|"GET /api/v1/voice/pipelines"| web
  catalog -->|"Opens first variant"| voice
  voice -->|"All STT: start and poll managed job; JSON recording or multipart file"| web
  voice -->|"All TTS: start job with input/voice, poll and fetch artifact"| web
  jobs -->|"GET /api/v1/jobs/audio/status"| web
  detail -->|"GET /api/v1/jobs/audio/{job_id}/status until terminal"| web
  stream -->|"SSE subscription"| web
  classDef internal fill:#1168bd,color:#fff,stroke:#0b4884
  classDef external fill:#666,color:#fff,stroke:#444
```

The route selects one STT or TTS pipeline view; there are no operation tabs.
STT sends a selected predefined recording as JSON, or an uploaded or recorded
file as multipart, to the managed run endpoint. Every UI STT and TTS
conversion uses a managed job polled through
`GET /api/v1/jobs/audio/{job_id}/status`; TTS retrieves its persisted artifact
after completion.

The Audio tab on the shared Jobs page polls oldest-first operational summaries.
Its detail view polls until `COMPLETED` or `FAILED`, then displays
the transcript or managed WAV link when available. `VoiceConversion` publishes
lifecycle notifications through the application-level Sonner toaster. These
notifications complement, rather than replace, inline errors and result panels.

`VoiceMetrics` does not read global service `/v1/performance` values. On desktop,
it and the always-visible platform `MetricsDashboard` share the right-hand rail;
on smaller viewports, that rail stacks below the active Voice workflow.
`MetricsProvider` is mounted at application level, so the dashboard does not
create another SSE subscription. The dashboard's local history is created on
mount and discarded on unmount; its hook keeps a 60-second window with updates
no more often than once per second.

## C4 Level 3: Backend Components

```mermaid
flowchart TB
  web["UI web server<br/>[Container: Nginx]<br/>Forwards Voice HTTP requests"]:::external
  automation["Automation client<br/>[External software system]<br/>Uses the public ViPPET API"]:::external
  subgraph api[Backend - Container]
    direction TB
    voiceroutes["Voice pipeline routes<br/>[Component: FastAPI / Pydantic]<br/>Catalog, recordings, 202 starts and artifact response"]:::internal
    jobsroutes["Audio Jobs routes<br/>[Component: FastAPI / Pydantic]<br/>List, status and stop for Audio jobs"]:::internal
    audiodependency["Audio job dependency<br/>[Component: FastAPI dependency]<br/>Provides the shared manager instance"]:::internal
    conversion["Voice conversion execution<br/>[Component: Python / wave]<br/>Validation, upstream calls and request timing"]:::internal
    adapter["Upstream service adapter<br/>[Component: httpx / asyncio / perf_counter]<br/>Bounded reads, errors, timeout, cleanup and timing"]:::internal
    assets["AudioAssetsManager<br/>[Component: Python / YAML / wave]<br/>Local recordings and managed paths"]:::internal
    audiocatalog["AudioPipelineManager<br/>[Component: Python / YAML]<br/>Strict preset definitions"]:::internal
    audiojobs["AudioPipelineJobManager<br/>[Component: asyncio]<br/>Locked process-local state, private STT staging, retention and atomic TTS artifacts"]:::internal
    modelapi["Model routes / ModelManager<br/>[Component: FastAPI / Python]<br/>Catalog, background jobs and installed state"]:::internal
    catalog["Voice model catalog<br/>[Component: DB-backed models / model_variants]<br/>Seeded from vippet/models/*.yaml; requests, variants and install state"]:::internal
    voiceroutes -->|"Start with JSON recording, JSON TTS, or multipart STT"| audiodependency
    voiceroutes -->|Read artifact metadata| audiodependency
    jobsroutes -->|Read snapshots and cancel| audiodependency
    audiodependency -->|Shared instance| audiojobs
    audiojobs -->|Execute managed STT or TTS| conversion
    conversion -->|Async call, bounded response| adapter
    voiceroutes -->|Lists pipeline definitions| audiocatalog
    audiojobs -->|Resolves pipeline and variant| audiocatalog
    audiojobs -->|Reads registered STT WAV; publishes TTS WAV| assets
    modelapi -->|Reads download requests and required variants| catalog
    modelapi -->|Persists variant and aggregate install state| catalog
  end
  asr["Audio Analyzer<br/>[External software system]<br/>Transcription service :8010"]:::external
  tts["Text to Speech<br/>[External software system]<br/>Synthesis service :8011"]:::external
  downloader["Model Download<br/>[External software system]<br/>Hugging Face plugin :8000"]:::external
  modelstore[("Shared model storage<br/>[External data store]<br/>shared/models/output PyTorch checkpoints")]:::external
  asrmodels[("voice_asr_models<br/>[External data store: named volume]<br/>Audio Analyzer OpenVINO models")]:::external
  ttsmodels[("voice_tts_models<br/>[External data store: named volume]<br/>Text to Speech OpenVINO models")]:::external
  audiostore[("Managed Audio storage<br/>[External data store]<br/>Registered STT input and UUID TTS output")]:::external
  web -->|"Catalog, managed starts and artifact"| voiceroutes
  web -->|"/api/v1/jobs/audio/*"| jobsroutes
  automation -->|"Managed jobs"| web
  web -->|"Model list, install and job status<br/>HTTP JSON"| modelapi
  adapter -->|"POST /v1/audio/transcriptions<br/>HTTP multipart; JSON response"| asr
  adapter -->|"POST /v1/audio/speech<br/>HTTP JSON; WAV response"| tts
  assets -->|"Managed input read and atomic output write"| audiostore
  voiceroutes -->|"Completed TTS FileResponse"| audiostore
  modelapi -->|"POST downloads with download_path=#quot;.#quot;; poll jobs"| downloader
  modelapi -->|"Checks catalog checkpoint exists<br/>(sets Installed)"| modelstore
  downloader -->|"Writes PyTorch checkpoints<br/>(not read by Voice services)"| modelstore
  asr -->|"Provisions on first start and loads own model"| asrmodels
  tts -->|"Provisions on first start and loads own model"| ttsmodels
  classDef internal fill:#1168bd,color:#fff,stroke:#0b4884
  classDef external fill:#666,color:#fff,stroke:#444
```

The Voice routes, conversion execution and upstream adapter reside in the Voice
router module. The Jobs router lists, reads and stops jobs through the same
`AudioPipelineJobManager` provided by dependency injection; neither router
imports the other.
`AudioPipelineJobManager`, `AudioPipelineManager` and `AudioAssetsManager` are
separate Python components in the same backend process.

The job manager guards its job and task maps with an `asyncio.Lock`. It returns
list snapshots oldest first by creation time and retains every active job plus
at most 500 terminal jobs. Evicting an older terminal TTS job removes its
managed artifact. Uploaded audio is first copied to a UUID-named file in a
manager-owned temporary directory and deleted on every exit path, then opened
for the validated conversion path. Predefined-recording STT opens the
registered WAV; TTS atomically publishes a UUID-named artifact.
Jobs expose service timing in `service_round_trip_ms`.
Model routes and `ModelManager` remain separate from the Voice router but run
in the same backend container.

## Flow: Voice Model Provisioning

Two independent paths provision Voice models. The catalog path decides whether
the UI enables Run; the service path provides the models that actually run.
Nothing orders or connects them.

```mermaid
sequenceDiagram
  autonumber
  actor Operator
  participant UI as Models page / browser
  participant API as ViPPET ModelManager
  participant Catalog as Models DB
  participant Download as Model Download
  participant Store as shared/models/output
  participant Hub as Hugging Face Hub
  participant Service as Audio Analyzer or Text to Speech
  participant Volume as voice_asr_models or voice_tts_models
  par Catalog install (gates Run)
    Operator->>UI: Install Whisper Base or SpeechT5
    UI->>API: POST /api/v1/models/download through Nginx
    API->>Catalog: Resolve download request and variants
    API-->>UI: 202 Accepted with ViPPET job ID
    API->>Download: POST /api/v1/models/download?download_path=.
    Download->>Hub: Download PyTorch checkpoint
    Download->>Store: Write huggingface/.../pytorch_model.bin
    loop Until the external job completes or fails
      API->>Download: GET /api/v1/jobs/{job_id}
      Download-->>API: Processing, completed or failed
      UI->>API: Poll ViPPET model job status through Nginx
      API-->>UI: Download progress
    end
    API->>Store: Check catalog checkpoint exists
    API->>Catalog: Persist variant and install state (Installed)
    Note over UI,Catalog: Audio pipeline Run is enabled when required_models are Installed
  and Service self-provisioning (used for inference)
    Service->>Volume: Look for a complete model
    alt First start or incomplete model
      Service->>Hub: Download Whisper Base or SpeechT5
      Service->>Service: Export to OpenVINO (int8 Whisper, fp16 SpeechT5)
      Service->>Volume: Store exported model
    end
    Service->>Volume: Load model
    Service->>Service: Compile for configured device and report healthy
  end
  Note over Store,Service: Voice services never read shared/models
```

The two paths share no state: starting the services before or after a catalog
install makes no difference to them, and a service that fails to provision its
model makes Audio jobs end as `FAILED` even when the catalog shows Installed.
Health and network requirements are listed in
[Deployment and Storage Boundaries](#deployment-and-storage-boundaries); the
resulting duplicate download is described in
[Known limitations](../user-guide/voice-conversion.md#known-limitations).

## Flow: Managed Speech to Text

```mermaid
sequenceDiagram
  autonumber
  actor Client as Browser UI or headless client
  participant Web as Nginx
  participant API as Audio pipeline routes
  participant Jobs as AudioPipelineJobManager
  participant Assets as AudioAssetsManager
  participant ASR as Audio Analyzer
  alt Predefined recording
    Client->>Web: POST .../speech-to-text/variants/{variant}/runs with JSON recording and language
    Web->>API: Forward JSON request
    API->>Jobs: start_job(pipeline, variant, recording)
  else Uploaded or recorded input
    Client->>Web: POST .../speech-to-text/variants/{variant}/runs with file and language
    Web->>API: Stream multipart request (Nginx limit 200 MiB)
    API->>Jobs: Stage random temporary file (backend limit 200 MiB) and start_job(pipeline, variant, input)
  end
  Jobs-->>API: RUNNING job with UUID
  API-->>Web: 202 Accepted with job_id
  Web-->>Client: Forward start response
  Jobs->>Jobs: Set RUNNING in process-local state
  alt Predefined recording
    Jobs->>Assets: Resolve registered WAV
    Assets-->>Jobs: Validated local path
  else Staged input
    Jobs->>Jobs: Open manager-owned temporary input
  end
  Jobs->>ASR: POST /v1/audio/transcriptions with WAV, language and device
  alt Success
    ASR-->>Jobs: Transcription JSON
    Jobs->>Jobs: Store transcript and timing, set COMPLETED, delete staged input
  else Upstream rejection, unavailability, timeout or invalid response
    ASR-->>Jobs: Error or no usable response
    Jobs->>Jobs: Log reason, set FAILED with fixed error, delete staged input
  end
  loop Until COMPLETED or FAILED
    Client->>Web: GET /api/v1/jobs/audio/{job_id}/status
    Web->>API: Forward status request
    API->>Jobs: Read process-local job
    Jobs-->>API: State, transcript and service timing
    API-->>Web: Job JSON
    Web-->>Client: Job JSON
  end
```

Managed STT accepts either a JSON body with a registered `recording` and a
two-letter `language`, or multipart `file` and `language` fields for uploaded
and recorded audio. The route stages multipart input before returning `202`; the
job owns and deletes that temporary input on every terminal path and shutdown.
Uploads are limited to 200 MiB in both places: Nginx applies
`client_max_body_size 200m` to the whole multipart request and usually rejects
an oversized upload first with its own HTML `413`; the backend applies
`MAX_STT_UPLOAD_BYTES` to the file content while staging and returns a JSON
`413`. Upstream errors occur after the `202` response, so the client sees them
only as a `FAILED` job with the fixed error text
`Audio pipeline execution failed.`.
The completed transcript and job metadata are process-local and disappear when
the backend restarts; no STT artifact is created.

## Flow: Managed Text to Speech

```mermaid
sequenceDiagram
  autonumber
  actor Client as Browser UI or headless client
  participant Web as Nginx
  participant API as Audio pipeline routes
  participant Jobs as AudioPipelineJobManager
  participant TTS as Text to Speech
  participant Store as shared/audio/output
  Client->>Web: POST .../text-to-speech/variants/{variant}/runs with input and voice
  Web->>API: Forward request
  API->>API: Validate 1-200 characters and supported voice
  API->>Jobs: start_job(pipeline, variant, input, voice)
  Jobs-->>API: RUNNING job with UUID
  API-->>Web: 202 Accepted with job_id
  Web-->>Client: Forward start response
  Jobs->>Jobs: Set RUNNING
  Jobs->>TTS: POST /v1/audio/speech with text, voice and device
  alt Success
    TTS-->>Jobs: WAV body
    Jobs->>Store: Write temporary file and atomically publish {job_id}.wav
    Jobs->>Jobs: Store artifact path and timing, set COMPLETED
  else Upstream rejection, unavailability, timeout or invalid response
    TTS-->>Jobs: Error or no usable response
    Jobs->>Jobs: Log reason, set FAILED with fixed error
  end
  loop Until COMPLETED or FAILED
    Client->>Web: GET /api/v1/jobs/audio/{job_id}/status
    Web->>API: Forward status request
    API-->>Web: Job JSON with artifact_url when complete
    Web-->>Client: Job JSON
  end
  Client->>Web: GET /api/v1/voice/jobs/{job_id}/artifact
  Web->>API: Forward artifact request
  API->>Store: Open completed job artifact
  Store-->>API: UUID WAV
  API-->>Web: audio/wav + Cache-Control no-store
  Web-->>Client: WAV artifact
```

Every TTS conversion started by the Audio pipeline UI follows this managed
path. The browser creates a blob URL only after downloading the persisted
artifact, then uses it for playback and download. Artifact retrieval, waveform
decoding and playback are excluded from the displayed managed request duration.
The proxy buffers the complete upstream body; TTS is not streaming playback or
a time-to-first-byte measurement.

## Flow: Conversion Timings and Telemetry

```mermaid
flowchart TB
    subgraph request[Per-conversion timings]
      direction TB
        BrowserStart[Browser performance.now before first fetch] --> HTTP[Voice run request through Nginx and backend]
        HTTP --> ServiceStart[Backend perf_counter before upstream context entry]
        ServiceStart --> ServiceBody[Connect, upload, queue, process and receive complete body]
        ServiceBody --> ServiceMs[Calculate elapsed milliseconds]
        ServiceMs --> Valid{Successful payload validation?}
        Valid -->|Yes| JobField[service_round_trip_ms in completed job]
        Valid -->|No| NoMetric[Job FAILED; panel enters failed state]
        JobField --> Parsed[Browser reads completed job status]
        Parsed --> RequestMs[Browser elapsed milliseconds]
        RequestMs --> Panel[Persistent Voice performance panel]
        JobField --> TimingCheck{Timing present?}
        TimingCheck -->|Yes| Panel
        TimingCheck -->|Missing| Unavailable[Show -- for service round trip]
        Unavailable --> Panel
    end
    subgraph platform[Continuous host-wide telemetry]
      direction TB
        Host[CPU, memory, GPU and NPU] --> Collectors[Telegraf and hardware collectors inside Metrics Manager]
        Collectors --> Manager[Metrics Manager]
        Manager --> Proxy[Nginx proxies SSE /metrics/stream]
        Proxy --> Stream[MetricsProvider / useMetricsStream EventSource]
        Stream --> Redux[Redux latest metric samples]
        Redux --> Dashboard[MetricsDashboard with useMetrics and local useMetricHistory]
        Dashboard --> Charts[Platform metrics section; no video FPS or pipeline latency]
    end
```

- **Request duration:** browser first-fetch start through the completed managed
  job status, including polling. TTS artifact retrieval occurs after this
  interval. The value remains browser-local.
- **Service round trip:** backend adapter start through complete upstream body
  reception and local response construction; excludes browser transfer and
  subsequent route payload validation/context cleanup. Includes transport,
  queueing and service processing, not only model inference.
- The intervals use independent monotonic clocks. No cross-machine timestamp
  subtraction or global last-request variable is needed.
- The Voice performance panel shows only the request-scoped timings returned in
  the completed job.
- Platform charts are live system-wide telemetry, not a frozen snapshot of a
  conversion and not resource attribution to a particular STT/TTS request.
- Voice does not query the services' global `last_ms` or `/v1/model-info` and does
  not report model inference time, chunk or segment counts, effective device,
  end-to-end conversational latency or time to first audio.

## Flow: Errors and Cancellation

```mermaid
flowchart TD
    Start[Start independent conversion; clear its previous result and timings] --> Active{Outcome}
    Active -->|Start request rejected by backend| StartError["HTTP 400, 404, 409, 415 or 422"]
    Active -->|Upload above 200 MiB| TooLarge["HTTP 413 from Nginx as HTML, or from backend as JSON"]
    StartError --> UIError
    TooLarge --> UIError
    Active -->|202 with valid job_id| Accepted[Own accepted job and show run started]
    Accepted --> Poll[Poll Audio job status]
    Poll -->|COMPLETED without transcript or artifact| Cancelled[Show run cancelled notification]
    Poll -->|COMPLETED and still current| Apply[Apply transcript or download and apply TTS artifact]
    Apply --> Complete[Show run completed notification]
    Poll -->|FAILED| JobFailed["Job error: Audio pipeline execution failed."]
    Poll -->|Status or artifact request failure| UIError
    JobFailed --> UIError[Display safe inline error and persistent failure notification]
    Upstream["Background job: upstream rejection, busy or unavailable service, 20-minute deadline or httpx timeout, invalid or oversized response"] -->|Reason logged in backend only| JobFailed
    Active -->|Local recording or capture error| LocalError[Display safe inline error; no job notification]
    Active -->|Stop button| StopJob{Job already accepted?}
    StopJob -->|Yes| StopApi[DELETE /api/v1/jobs/audio/job_id cancels the backend task]
    StopApi --> Poll
    StopJob -->|No| Discard[AbortController discards pre-acceptance work]
    Active -->|Microphone Cancel| Abort[AbortController stops local recording]
    Active -->|Start replacement| Supersede[Abort and silently discard superseded response]
    Active -->|Navigate away| Unmount[Abort and silently discard on unmount]
    Active -->|1210-second browser timer, including polling| Deadline["Stop polling with Conversion timed out."]
    Deadline --> UIError
    Deadline -.->|No DELETE is sent| Orphan[Backend job keeps running and can still complete]
```

Run requests return `202` as soon as the job is accepted. Only request
validation, unknown pipelines, variants or recordings, an unavailable
pipeline, and oversized uploads produce HTTP errors. Everything that happens
while calling Audio Analyzer or Text to Speech happens inside the background
job: the job manager logs the exception type and sanitized reason and sets the
job to `FAILED` with the fixed error text `Audio pipeline execution failed.`.
The adapter's internal status mapping (`400`, `502`, `503`, `504`) is not
returned to clients.

Stop on an accepted job cancels the managed backend task through
`AudioPipelineJobManager.cancel_job`: the job moves to `COMPLETED` without a
result (or to `FAILED` when cancelling raises an error), the in-flight
request to the upstream service is cancelled, and staged input and any
uncommitted artifact are removed. It cannot guarantee that an already-started
upstream inference stops. Navigating away does not cancel a managed job, which
can still finish and persist its WAV. Backend contexts
close resources on return or exceptions; their total upstream deadline is 20
minutes, with a 5-second connection timeout.

The browser keeps a 1210-second timer for the whole run, including polling.
When it fires, the UI stops polling and shows `Conversion timed out.`, but it
does not send `DELETE`, so the backend job keeps running and can still
complete. The Nginx Voice read and send timeouts are also 1210 seconds; they
apply only to the individual start, status and artifact requests, none of which
wait for the conversion. Proxy-generated failures, such as the Nginx `413`
described in [Flow: Managed Speech to Text](#flow-managed-speech-to-text), use
Nginx's own response format.

## Implementation References

- [Voice workflow](../../../ui/src/features/voice/VoiceConversion.tsx),
  [pipeline variant selector](../../../ui/src/features/pipelines/PipelineVariantSelect.tsx),
  [recording adapter](../../../ui/src/features/voice/recording.ts),
  [audio preview](../../../ui/src/features/voice/VoiceAudio.tsx) and
  [performance panel](../../../ui/src/features/voice/VoiceMetrics.tsx).
- [Jobs page](../../../ui/src/pages/Jobs.tsx),
  [Audio job detail](../../../ui/src/pages/AudioJobDetail.tsx),
  [application layout and toaster](../../../ui/src/components/Layout.tsx),
  [Voice API and upstream adapter](../../../vippet/api/routes/voice.py),
  [Jobs API adapter](../../../vippet/api/routes/jobs.py) and
  [Audio job dependency](../../../vippet/api/dependencies/audio_jobs.py).
- [Audio pipeline manager](../../../vippet/managers/audio_pipeline_manager.py),
  [job manager](../../../vippet/managers/audio_pipeline_job_manager.py) and
  [managed Audio assets](../../../vippet/audio_assets.py).
- [Models page](../../../ui/src/pages/Models.tsx),
  [model installation hook](../../../ui/src/features/models/useModelInstall.ts),
  [model routes](../../../vippet/api/routes/models.py),
  [model manager](../../../vippet/managers/model_manager.py),
  [Whisper catalog entry](../../../vippet/models/voice-whisper-base.yaml),
  [SpeechT5 catalog entry](../../../vippet/models/voice-speecht5.yaml),
  [Speech to Text](../../../vippet/pipelines/speech-to-text.yaml) and
  [Text to Speech](../../../vippet/pipelines/text-to-speech.yaml) pipeline
  definitions with `required_models`, and
  [catalog DB seeding](../../../vippet/db_seed.py).
- Voice service model provisioning:
  [Audio Analyzer](../../../../../microservices/audio-analyzer/utils/provision_models.py),
  [Text to Speech](../../../../../microservices/text-to-speech/utils/ensure_model.py) and
  [SpeechT5 preparation](../../../../../microservices/text-to-speech/utils/ensure_speecht5.py).
- [Metrics stream](../../../ui/src/hooks/useMetricsStream.ts),
  [local chart history](../../../ui/src/hooks/useMetricHistory.ts) and
  [shared dashboard](../../../ui/src/features/metrics/MetricsDashboard.tsx).
- [Nginx routing](../../../ui/nginx.conf),
  [Compose configuration](../../../compose.yml) with the
  [GPU](../../../compose.gpu.yml), [NPU](../../../compose.npu.yml) and
  [WSL GPU](../../../compose.gpu-wsl.yml) overrides,
  [Make targets](../../../Makefile) and
  [system telemetry architecture](./metrics/system-performance.md).
- [Voice user guide](../user-guide/voice-conversion.md),
  [backend regression tests](../../../vippet/tests/unit/api_tests/voice_test.py).
