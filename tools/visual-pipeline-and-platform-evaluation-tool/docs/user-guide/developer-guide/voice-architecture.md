<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Voice Architecture: STT, TTS and Metrics

These diagrams describe the implemented Voice integration as of 2026-09-24.
They follow the [C4 model](https://c4model.com/diagrams) at System Context,
Container and Component levels only. Flow diagrams describe runtime behavior;
there is no Code-level diagram.

## Scope and Notation

- The system of interest is ViPPET. Audio Analyzer, Text to Speech, Model
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
  operator["Operator<br/>[Person]<br/>Converts speech/text and reviews metrics"]:::person
  vippet["ViPPET<br/>[Software system]<br/>Voice conversion and performance visualization"]:::internal
  asr["Audio Analyzer<br/>[External software system]<br/>Transcribes recordings"]:::external
  tts["Text to Speech<br/>[External software system]<br/>Synthesizes speech"]:::external
  models["Model Download<br/>[External software system]<br/>Downloads and exports Voice models"]:::external
  telemetry["Metrics Manager<br/>[External software system]<br/>Collects host-wide telemetry"]:::external
  operator -->|Uses web UI| vippet
  vippet -->|Recording to transcript| asr
  vippet -->|Text to audio| tts
  vippet -->|Requests Voice model installation| models
  vippet -->|Subscribes to platform metrics| telemetry
  classDef person fill:#08427b,color:#fff,stroke:#052e56
  classDef internal fill:#1168bd,color:#fff,stroke:#0b4884
  classDef external fill:#666,color:#fff,stroke:#444
```

The operator normally uses the ViPPET UI. Direct upstream API access is possible
through published service ports, but bypasses the ViPPET proxy and its controls.

## C4 Level 2: Containers

```mermaid
flowchart TB
  operator["Operator<br/>[Person]"]:::person
  subgraph vippet[ViPPET - System]
    direction TB
    spa["Browser UI<br/>[Container: React / TypeScript]<br/>Voice workflow, model installation and metrics"]:::internal
    web["UI web server<br/>[Container: Nginx :80]<br/>Serves assets and proxies API / SSE"]:::internal
    api["Backend<br/>[Container: FastAPI / Python :7860]<br/>Voice proxy, model jobs and validation"]:::internal
    spa -->|"Assets, API requests and SSE<br/>HTTP; HTTPS at deployment edge"| web
    web -->|"/api/v1/voice/* and model APIs<br/>HTTP :7860"| api
  end
  asr["Audio Analyzer<br/>[External software system]<br/>Whisper Base / OpenVINO"]:::external
  tts["Text to Speech<br/>[External software system]<br/>SpeechT5 / OpenVINO"]:::external
  downloader["Model Download<br/>[External software system :8000]<br/>OpenVINO download and export jobs"]:::external
  modelstore[("Shared Voice model storage<br/>[External data store]<br/>shared/models/output/voice")]:::external
  telemetry["Metrics Manager<br/>[External software system]<br/>FastAPI, Telegraf and hardware collectors"]:::external
  operator -->|Browser interaction| spa
  api -->|"POST /v1/audio/transcriptions<br/>HTTP multipart :8010; JSON response"| asr
  api -->|"POST /v1/audio/speech<br/>HTTP JSON :8011; WAV response"| tts
  api -->|"Start and poll model jobs<br/>HTTP JSON :8000"| downloader
  api -->|"Reads catalog and installed state"| modelstore
  downloader -->|"Writes exported OpenVINO artifacts"| modelstore
  asr -->|"Loads Whisper artifacts read-only"| modelstore
  tts -->|"Loads SpeechT5 artifacts read-only"| modelstore
  web -->|"GET /metrics/stream<br/>HTTP / SSE :9090"| telemetry
  classDef person fill:#08427b,color:#fff,stroke:#052e56
  classDef internal fill:#1168bd,color:#fff,stroke:#0b4884
  classDef external fill:#666,color:#fff,stroke:#444
```

Nginx enforces an 11 MiB Voice request-body limit and disables response caching.
The backend imposes its own input, response-size and deadline limits. It does not
forward upstream error bodies or environment HTTP proxy settings to these calls.

### Deployment and Storage Boundaries

- The current Compose file publishes `8010:8010` and `8011:8011` without a
  loopback host address. Network reachability depends on the host/firewall;
  these bindings are not restricted to localhost by this configuration.
  Protect direct access with deployment-level access control and TLS.
- The Models page starts ViPPET background jobs for Whisper Base and SpeechT5.
  `ModelManager` forwards their OpenVINO requests to Model Download, polls the
  returned jobs and tracks installed state. SpeechT5 installs INT8 and FP16 in
  one ViPPET job.
- Model Download exports device-neutral OpenVINO artifacts on CPU under
  `shared/models/output/voice`. Audio Analyzer and Text to Speech mount the
  shared model tree read-only and compile the selected artifact for the runtime
  device when they load it.
- ASR keeps runtime cache, chunks and storage in `voice_asr_cache`,
  `voice_asr_chunks` and `voice_asr_storage`. Recordings/transcripts can persist
  in its storage volume; clear-on-startup is enabled, not a per-request retention
  guarantee. TTS keeps runtime cache and storage in `voice_tts_cache` and
  `voice_tts_storage`, but `PERSIST_OUTPUTS=false` disables output persistence.
- ViPPET does not persist Voice content or request timings. Completed results
  and timings live in React state; each tab retains its latest result until
  replacement, input changes or unmount. Blob URLs are revoked during cleanup.
- Hardware overrides determine the default service devices and which device
  nodes are mounted. Per-request Voice overrides select among compatible,
  visible devices. Telemetry reflects the whole host and can include unrelated
  workloads on those devices.

## C4 Level 3: Browser UI Components

```mermaid
flowchart TB
  web["UI web server<br/>[Container: Nginx]<br/>Voice API and SSE proxy"]:::external
  subgraph spa[Browser UI - Container]
    direction TB
    voice["VoiceConversion<br/>[Component: React]<br/>Inputs, fetch, timing and cancellation"]:::internal
    device["VoiceDeviceSelect<br/>[Component: React]<br/>Available CPU/GPU/NPU families and service default"]:::internal
    recorder["Recording adapter<br/>[Component: Web Audio]<br/>captureWav prepares local PCM WAV"]:::internal
    audio["VoiceAudio<br/>[Component: Web Audio / Recharts]<br/>Waveform and native audio playback"]:::internal
    timings["VoiceMetrics<br/>[Component: React]<br/>Successful request/service timings"]:::internal
    stream["MetricsProvider / useMetricsStream<br/>[Component: EventSource]<br/>Shared SSE subscription and reconnect"]:::internal
    store["Metrics state<br/>[Component: Redux Toolkit]<br/>Current samples and connection state"]:::internal
    dashboard["MetricsDashboard<br/>[Component: React / Recharts]<br/>useMetrics and useMetricHistory"]:::internal
    cards["MetricCard<br/>[Component: React]<br/>Shared numeric presentation"]:::internal
    voice -->|Async capture, AbortSignal| recorder
    voice -->|Selected request override| device
    device -->|Reads available device families| store
    voice -->|Blob URL props| audio
    voice -->|Timing props| timings
    timings -->|Duration props| cards
    voice -->|Mounts on expand, no video metrics| dashboard
    stream -->|Dispatches Redux actions| store
    dashboard -->|Reads Redux selectors| store
    dashboard -->|Renders platform values| cards
  end
  voice -->|"fetch POST /api/v1/voice/*<br/>HTTP multipart or JSON"| web
  stream -->|"SSE subscription"| web
  classDef internal fill:#1168bd,color:#fff,stroke:#0b4884
  classDef external fill:#666,color:#fff,stroke:#444
```

`VoiceMetrics` does not read global service `/v1/performance` values and does not
send timings to Metrics Manager. `MetricsProvider` is mounted at application
level, so expanding the Voice dashboard does not create another SSE subscription.
The dashboard's local history is created on mount and discarded on unmount; its
hook keeps a 60-second window with updates no more often than once per second.

## C4 Level 3: Backend Components

```mermaid
flowchart TB
  web["UI web server<br/>[Container: Nginx]<br/>Forwards Voice HTTP requests"]:::external
  subgraph api[Backend - Container]
    direction TB
    stt["Transcription endpoint<br/>[Component: FastAPI / Pydantic / wave]<br/>Upload, language, WAV and transcript validation"]:::internal
    speech["Speech endpoint<br/>[Component: FastAPI / Pydantic]<br/>Text validation and WAV signature checks"]:::internal
    adapter["Upstream service adapter<br/>[Component: httpx / asyncio / perf_counter]<br/>Bounded reads, errors, timeout, cleanup and timing"]:::internal
    modelapi["Model routes / ModelManager<br/>[Component: FastAPI / Python]<br/>Catalog, background jobs and installed state"]:::internal
    catalog["Voice model catalog<br/>[Component: supported_models.yaml]<br/>Whisper and SpeechT5 requests and artifacts"]:::internal
    stt -->|Async call, response cap 128 KiB| adapter
    speech -->|Async call, response cap 64 MiB| adapter
    modelapi -->|Resolves requests and required artifacts| catalog
  end
  asr["Audio Analyzer<br/>[External software system]<br/>Transcription service :8010"]:::external
  tts["Text to Speech<br/>[External software system]<br/>Synthesis service :8011"]:::external
  downloader["Model Download<br/>[External software system]<br/>OpenVINO plugin :8000"]:::external
  modelstore[("Shared Voice model storage<br/>[External data store]<br/>OpenVINO artifacts and installed registry")]:::external
  web -->|"POST /api/v1/voice/transcriptions<br/>HTTP multipart"| stt
  web -->|"POST /api/v1/voice/speech<br/>HTTP JSON"| speech
  web -->|"Model list, install and job status<br/>HTTP JSON"| modelapi
  adapter -->|"POST /v1/audio/transcriptions<br/>HTTP multipart; JSON response"| asr
  adapter -->|"POST /v1/audio/speech<br/>HTTP JSON; WAV response"| tts
  modelapi -->|"POST downloads; poll jobs"| downloader
  modelapi -->|"Checks artifacts; records installed state"| modelstore
  downloader -->|"Exports into voice target path"| modelstore
  asr -->|"Loads model read-only"| modelstore
  tts -->|"Loads model read-only"| modelstore
  classDef internal fill:#1168bd,color:#fff,stroke:#0b4884
  classDef external fill:#666,color:#fff,stroke:#444
```

The Voice endpoints and upstream adapter currently reside in the same router
module. The adapter is `call_service` with `create_client`; WAV input validation
is `validate_audio`. The routes publish `X-Voice-Service-Duration-Ms` only after
successful payload validation. There is no shared mutable timing value between
requests. Model routes and `ModelManager` are separate from the Voice router but
run in the same backend container.

## Flow: Install Voice Models

```mermaid
sequenceDiagram
  autonumber
  actor Operator
  participant UI as Models page / browser
  participant Web as Nginx
  participant API as ViPPET ModelManager
  participant Download as Model Download
  participant Store as shared/models/output/voice
  participant Service as Audio Analyzer or Text to Speech
  Operator->>UI: Install Whisper Base or SpeechT5
  UI->>Web: POST /api/v1/models/download
  Web->>API: Forward model names
  API->>API: Validate catalog entry, installed state and running jobs
  API-->>Web: 202 Accepted with ViPPET job ID
  Web-->>UI: Forward response
  API->>Download: POST /api/v1/models/download?download_path=voice
  Note over API,Download: Whisper starts one export while SpeechT5 starts INT8 and FP16 exports
  Download->>Store: Stage and publish complete OpenVINO artifacts
  loop Until all external jobs complete or fail
    API->>Download: GET /api/v1/jobs/{job_id}
    Download-->>API: Processing, completed or failed
    UI->>Web: Poll ViPPET model job status
    Web->>API: Forward status request
    API-->>Web: Aggregated progress
    Web-->>UI: Forward status response
  end
  API->>Store: Verify required artifacts and record Installed state
  Note over Service,Store: Voice services must start after installation
  Service->>Store: Load selected precision read-only
  Service->>Service: Compile for configured or per-request device
```

Voice services do not download models during startup. They preload models, so
starting them before installation makes their health checks fail until the
required artifacts exist and the services restart. Model Download stages
exports before publishing complete artifacts; subsequent starts reuse them.

## Flow: Speech to Text

```mermaid
sequenceDiagram
    autonumber
    actor Operator
    participant UI as VoiceConversion / browser
    participant Capture as captureWav / Web Audio
    participant Web as Nginx
    participant API as ViPPET Voice API
    participant ASR as Audio Analyzer
    alt Microphone source
        Operator->>UI: Record and grant permission
        UI->>Capture: captureWav(signal)
        Note over UI,Capture: Local recording, not an inference request
        Operator->>Capture: Stop (or automatic 60-second limit)
        Capture->>Capture: Release microphone, decode and encode mono PCM16 / 16 kHz
        Capture-->>UI: recording.wav
    else File source
        Operator->>UI: Select WAV (non-empty, up to 10 MiB)
    end
    Operator->>UI: Transcribe
    UI->>UI: Clear STT result/timings, start performance.now()
    UI->>Web: POST /api/v1/voice/transcriptions (file, language, optional device)
    Web->>API: Forward multipart request (11 MiB envelope limit)
    API->>API: Validate size, language and mono PCM16 WAV / 8-48 kHz / up to 60 s
    API->>API: Start perf_counter(), enter upstream timeout
    API->>ASR: POST /v1/audio/transcriptions (file, language, JSON format, optional device)
    ASR->>ASR: Validate device and compile or reuse its cached model
    ASR-->>API: Transcription JSON body
    API->>API: Receive full body (up to 128 KiB), calculate service duration
    API->>API: Close upstream resources, validate transcript
    API-->>Web: JSON text + timing header + Cache-Control no-store
    Web-->>UI: Same body and timing header
    UI->>UI: Parse JSON, check abort/current request, calculate request duration
    UI-->>Operator: Transcription + VoiceMetrics
```

The sequence shows the successful path. WAV preparation is excluded from both
request metrics. The adapter closes its contexts before control returns to the
endpoint for transcript validation; cleanup order is stream, client, timeout.

## Flow: Text to Speech

```mermaid
sequenceDiagram
    autonumber
    actor Operator
    participant UI as VoiceConversion / browser
    participant Web as Nginx
    participant API as ViPPET Voice API
    participant TTS as Text to Speech
    participant Audio as VoiceAudio / browser
    Operator->>UI: Enter text or select sample, Generate speech
    UI->>UI: Clear TTS result/timings, start performance.now()
    UI->>Web: POST /api/v1/voice/speech (JSON input, optional device)
    Web->>API: Forward request
    API->>API: Trim text, validate 1-5000 characters, reject extra fields
    API->>API: Start perf_counter(), enter upstream timeout
    API->>TTS: POST /v1/audio/speech (input, response_format=wav, optional device)
    TTS->>TTS: Validate device and compile or reuse its cached model
    TTS->>TTS: Synthesize using selected device and voice
    TTS-->>API: WAV body
    API->>API: Receive full body (up to 64 MiB), calculate service duration
    API->>API: Close upstream resources, check MIME type and RIFF/WAVE signature
    API-->>Web: audio/wav + timing header + Cache-Control no-store
    Web-->>UI: WAV body and timing header
    UI->>UI: Read Blob, check abort/current request, calculate request duration
    UI-->>Operator: VoiceMetrics for this successful conversion
    UI->>Audio: Create and supply blob URL
    Audio->>Audio: Decode locally, derive peaks, scale display to sampled maximum
    Audio-->>Operator: Waveform and native audio player
    Operator->>Audio: Play, seek or pause
    Operator->>UI: Download original WAV via blob URL
```

Waveform decoding, display normalization and playback are excluded from the
reported request duration. Normalization changes only the plot, not the audio
bytes or volume. A visualization failure does not disable playback or download.
The proxy buffers the entire upstream body; this is not streaming playback or a
time-to-first-byte measurement.

## Flow: Two Independent Metrics Paths

```mermaid
flowchart TB
    subgraph request[Per-conversion timings]
      direction TB
        BrowserStart[Browser performance.now before fetch] --> HTTP[Voice POST through Nginx and backend]
        HTTP --> ServiceStart[Backend perf_counter before upstream context entry]
        ServiceStart --> ServiceBody[Connect, upload, queue, process and receive complete body]
        ServiceBody --> ServiceMs[Calculate elapsed milliseconds]
        ServiceMs --> Valid{Successful payload validation?}
        Valid -->|Yes| Header[X-Voice-Service-Duration-Ms on same response]
        Valid -->|No| NoMetric[HTTP error; no successful result or timing cards]
        Header --> Parsed[Browser reads full JSON or Blob and checks current request]
        Parsed --> RequestMs[Browser elapsed milliseconds]
        RequestMs --> Cards[VoiceMetrics reuses MetricCard]
        Header --> HeaderCheck{Finite non-negative decimal header?}
        HeaderCheck -->|Yes| Cards
        HeaderCheck -->|Missing or invalid| Unavailable[Service round trip unavailable; keep request duration]
        Unavailable --> Cards
    end
    subgraph platform[Continuous host-wide telemetry]
      direction TB
        Host[CPU, memory, GPU and NPU] --> Collectors[Telegraf and hardware collectors inside Metrics Manager]
        Collectors --> Manager[Metrics Manager normalizes telemetry]
        Manager --> Proxy[Nginx proxies SSE /metrics/stream]
        Proxy --> Stream[MetricsProvider / useMetricsStream EventSource]
        Stream --> Redux[Redux metrics samples and connection state]
        Redux --> Dashboard[MetricsDashboard with useMetrics and local useMetricHistory]
        Dashboard --> Charts[Platform metrics section; no video FPS or pipeline latency]
    end
```

No arrow connects Voice timing cards to the telemetry ingestion path: this
integration does not persist or publish request timings to Metrics Manager.
The services' global `last_ms` and `/v1/model-info` are not queried by Voice.

- **Request duration:** browser fetch start through complete response consumption
  and success checks, including upload, proxy handling, service work and download.
- **Service round trip:** backend adapter start through complete upstream body
  reception and local response construction; excludes browser transfer and
  subsequent route payload validation/context cleanup. Includes transport,
  queueing and service processing, not only model inference.
- The intervals use independent monotonic clocks. No cross-machine timestamp
  subtraction or global last-request variable is needed.
- Platform charts are live system-wide telemetry, not a frozen snapshot of a
  conversion and not resource attribution to a particular STT/TTS request.

## Flow: Errors and Cancellation

```mermaid
flowchart TD
    Start[Start independent conversion; clear its previous result and timings] --> Active{Outcome}
    Active -->|Success and still current| Publish[Publish result and request metrics]
    Active -->|Local input or capture error| UIError[Display safe error; no new result]
    Active -->|Cancel or tab switch| Abort[AbortController aborts browser work]
    Active -->|130-second browser deadline| Deadline[Abort with timeout message]
    Active -->|Navigate away| Unmount[Abort on unmount; release browser state]
    Abort --> Discard[Discard late or superseded response]
    Deadline --> UIError
    Unmount --> Discard
    Active -->|Backend or proxy failure| Status{Failure class}
    Status -->|Invalid input| Input[400 or 422; oversized input 413]
    Status -->|Upstream 400 / 413 / 422| Rejected[400 sanitized rejection]
    Status -->|Upstream 429 or HTTP transport error| Unavailable[503 busy or unavailable]
    Status -->|120-second upstream deadline or httpx timeout| Timeout[504 timeout]
    Status -->|Other upstream status, invalid payload or response too large| BadGateway[502 sanitized service failure]
    Input --> UIError
    Rejected --> UIError
    Unavailable --> UIError
    Timeout --> UIError
    BadGateway --> UIError
```

Cancellation stops browser recording/fetch and prevents stale results from being
published. It does **not** guarantee that an already-started upstream inference
stops. Backend contexts close resources on return or exceptions; their total
upstream deadline is 120 seconds, with a 5-second connection timeout. Nginx Voice
read/send timeouts are 130 seconds, separate from the browser's 130-second timer.
Proxy-generated failures may differ from the backend's status mapping above.

## Implementation References

- [Voice workflow](../../../ui/src/features/voice/VoiceConversion.tsx),
  [recording adapter](../../../ui/src/features/voice/recording.ts),
  [audio preview](../../../ui/src/features/voice/VoiceAudio.tsx) and
  [request timing cards](../../../ui/src/features/voice/VoiceMetrics.tsx).
- [Voice API and upstream adapter](../../../vippet/api/routes/voice.py).
- [Models page](../../../ui/src/pages/Models.tsx),
  [model installation hook](../../../ui/src/features/models/useModelInstall.ts),
  [model routes](../../../vippet/api/routes/models.py),
  [model manager](../../../vippet/managers/model_manager.py) and
  [supported model catalog](../../../shared/models/supported_models.yaml).
- [Metrics stream](../../../ui/src/hooks/useMetricsStream.ts),
  [local chart history](../../../ui/src/hooks/useMetricHistory.ts) and
  [shared dashboard](../../../ui/src/features/metrics/MetricsDashboard.tsx).
- [Nginx routing](../../../ui/nginx.conf),
  [Voice Compose configuration](../../../compose.voice.yml) and
  [system telemetry architecture](./metrics/system-performance.md).
- [Voice user guide](../user-guide/voice-conversion.md),
  [backend regression tests](../../../vippet/tests/unit/api_tests/voice_test.py) and
  [browser regression tests](../../../ui/tests/voice.spec.ts).
