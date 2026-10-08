<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Voice Architecture: STT, TTS and Metrics

These diagrams describe the implemented Voice integration as of 2026-10-08.
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
  telemetry["Metrics Manager<br/>[External software system]<br/>Collects platform telemetry and Voice timings"]:::external
  operator -->|Uses web UI| vippet
  vippet -->|Recording to transcript| asr
  vippet -->|Text to audio| tts
  vippet -->|Requests Voice model installation| models
  vippet -->|Publishes Voice timings and subscribes to platform metrics| telemetry
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
  telemetry["Metrics Manager<br/>[External software system]<br/>Custom metrics API, SSE, Telegraf and hardware collectors"]:::external
  operator -->|Browser interaction| spa
  api -->|"POST /v1/audio/transcriptions<br/>HTTP multipart :8010; JSON response"| asr
  api -->|"POST /v1/audio/speech<br/>HTTP JSON :8011; WAV response"| tts
  api -->|"Start and poll model jobs<br/>HTTP JSON :8000"| downloader
  api -->|"Reads catalog and installed state"| modelstore
  downloader -->|"Writes exported OpenVINO artifacts"| modelstore
  asr -->|"Loads Whisper artifacts read-only"| modelstore
  tts -->|"Loads SpeechT5 artifacts read-only"| modelstore
  api -->|"POST /api/v1/metrics<br/>Voice service round-trip timings :9090"| telemetry
  web -->|"GET /metrics/stream<br/>HTTP / SSE :9090"| telemetry
  classDef person fill:#08427b,color:#fff,stroke:#052e56
  classDef internal fill:#1168bd,color:#fff,stroke:#0b4884
  classDef external fill:#666,color:#fff,stroke:#444
```

Nginx streams Voice request bodies without imposing a separate upload-size
limit and disables response caching. The backend preserves upload metadata and
streams the spooled file to Audio Analyzer, which owns input validation. The
backend retains response-size and deadline limits. It forwards only known
file-validation messages from bounded Audio Analyzer error responses; all other
upstream details remain hidden. Environment HTTP proxy settings are not used for
these calls.

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
- ViPPET does not persist Voice content. Completed results and per-conversion
  timings live in React state; each tab retains its latest result until
  replacement, input changes or unmount. The backend service round trip is also
  published to Metrics Manager's runtime store, not to a durable request log.
  Blob URLs are revoked during cleanup.
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
    timings["VoiceMetrics<br/>[Component: React]<br/>Request and service round-trip timings"]:::internal
    stream["MetricsProvider / useMetricsStream<br/>[Component: EventSource]<br/>Shared SSE subscription and reconnect"]:::internal
    store["Metrics state<br/>[Component: Redux Toolkit]<br/>Current samples and connection state"]:::internal
    dashboard["MetricsDashboard<br/>[Component: React / Recharts]<br/>useMetrics and useMetricHistory"]:::internal
    cards["MetricCard<br/>[Component: React]<br/>Shared numeric presentation"]:::internal
    voice -->|Async capture, AbortSignal| recorder
    voice -->|Selected request override| device
    device -->|Reads available device families| store
    voice -->|Blob URL props| audio
    voice -->|Timing props| timings
    voice -->|Always mounts below VoiceMetrics in right rail; no video metrics| dashboard
    stream -->|Dispatches Redux actions| store
    dashboard -->|Reads Redux selectors| store
    dashboard -->|Renders platform values| cards
  end
  voice -->|"fetch POST /api/v1/voice/*<br/>HTTP multipart or JSON"| web
  stream -->|"SSE subscription"| web
  classDef internal fill:#1168bd,color:#fff,stroke:#0b4884
  classDef external fill:#666,color:#fff,stroke:#444
```

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
  subgraph api[Backend - Container]
    direction TB
    stt["Transcription endpoint<br/>[Component: FastAPI / Pydantic / wave]<br/>Upload, language, WAV and transcript validation"]:::internal
    speech["Speech endpoint<br/>[Component: FastAPI / Pydantic]<br/>Text validation and WAV signature checks"]:::internal
    adapter["Upstream service adapter<br/>[Component: httpx / asyncio / perf_counter]<br/>Bounded reads, errors, timeout, cleanup and timing"]:::internal
    publisher["Voice metrics publisher<br/>[Component: asyncio / httpx]<br/>Best-effort service round-trip publication"]:::internal
    modelapi["Model routes / ModelManager<br/>[Component: FastAPI / Python]<br/>Catalog, background jobs and installed state"]:::internal
    catalog["Voice model catalog<br/>[Component: DB-backed models / model_variants]<br/>Seeded from vippet/models/*.yaml; requests, variants and install state"]:::internal
    stt -->|Async call, response cap 128 KiB| adapter
    speech -->|Async call, response cap 64 MiB| adapter
    stt -->|Schedules validated ASR timing| publisher
    speech -->|Schedules validated TTS timing| publisher
    modelapi -->|Reads download requests and required variants| catalog
    modelapi -->|Persists variant and aggregate install state| catalog
  end
  asr["Audio Analyzer<br/>[External software system]<br/>Transcription service :8010"]:::external
  tts["Text to Speech<br/>[External software system]<br/>Synthesis service :8011"]:::external
  telemetry["Metrics Manager<br/>[External software system]<br/>Custom metrics API :9090"]:::external
  downloader["Model Download<br/>[External software system]<br/>OpenVINO plugin :8000"]:::external
  modelstore[("Shared Voice model storage<br/>[External data store]<br/>OpenVINO artifacts")]:::external
  web -->|"POST /api/v1/voice/transcriptions<br/>HTTP multipart"| stt
  web -->|"POST /api/v1/voice/speech<br/>HTTP JSON"| speech
  web -->|"Model list, install and job status<br/>HTTP JSON"| modelapi
  adapter -->|"POST /v1/audio/transcriptions<br/>HTTP multipart; JSON response"| asr
  adapter -->|"POST /v1/audio/speech<br/>HTTP JSON; WAV response"| tts
  publisher -->|"POST /api/v1/metrics<br/>HTTP JSON; 2-second timeout"| telemetry
  modelapi -->|"POST downloads; poll jobs"| downloader
  modelapi -->|"Checks required artifacts"| modelstore
  downloader -->|"Exports into voice target path"| modelstore
  asr -->|"Loads model read-only"| modelstore
  tts -->|"Loads model read-only"| modelstore
  classDef internal fill:#1168bd,color:#fff,stroke:#0b4884
  classDef external fill:#666,color:#fff,stroke:#444
```

The Voice endpoints, upstream adapter and metrics publisher currently reside in
the same router module. The adapter is `call_service` with `create_client`;
uploaded audio is streamed to Audio Analyzer for validation. After successful
payload validation, each route returns `X-Voice-Service-Duration-Ms` and
schedules a best-effort publish to Metrics Manager. Publication failures do not
fail the conversion response. There is no shared mutable timing value between
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
  participant Catalog as Models DB
  participant Download as Model Download
  participant Store as shared/models/output/voice
  participant Service as Audio Analyzer or Text to Speech
  Operator->>UI: Install Whisper Base or SpeechT5
  UI->>Web: POST /api/v1/models/download
  Web->>API: Forward model names
  API->>Catalog: Resolve requests, variants and current install state
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
  API->>Store: Verify required artifacts
  API->>Catalog: Persist variant and aggregate install state
  Note over API,Catalog: SpeechT5 is Installed only when INT8 and FP16 are complete
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
    participant Metrics as Metrics Manager
    alt Microphone source
        Operator->>UI: Record and grant permission
        UI->>Capture: captureWav(signal)
        Note over UI,Capture: Local recording, not an inference request
        Operator->>Capture: Stop (or automatic 60-second limit)
        Capture->>Capture: Release microphone, decode and encode mono PCM16 / 16 kHz
        Capture-->>UI: recording.wav
    else File source
      Operator->>UI: Select audio file
    end
    Operator->>UI: Transcribe
    UI->>UI: Clear STT result/timings, start performance.now()
    UI->>Web: POST /api/v1/voice/transcriptions (file, language, optional device)
    Web->>API: Stream multipart request without a separate size limit
    API->>API: Validate language and retain original file metadata
    API->>API: Start perf_counter(), enter upstream timeout
    API->>ASR: POST /v1/audio/transcriptions (file, language, JSON format, optional device)
    ASR->>ASR: Validate file and device, compile or reuse its cached model
    ASR-->>API: Transcription JSON body
    API->>API: Receive full body (up to 128 KiB), calculate service duration
    API->>API: Close upstream resources, validate transcript
    API-->>Metrics: Best-effort voice_asr service round trip with requested device and language
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
    participant Metrics as Metrics Manager
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
    API-->>Metrics: Best-effort voice_tts service round trip with requested device and voice
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

## Flow: Conversion Timings and Telemetry

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
        Valid -->|Yes| Publish[Schedule non-blocking metric publish]
        Valid -->|No| NoMetric[HTTP error; persistent panel enters failed state]
        Header --> Parsed[Browser reads full JSON or Blob and checks current request]
        Parsed --> RequestMs[Browser elapsed milliseconds]
        RequestMs --> Panel[Persistent Voice performance panel]
        Header --> HeaderCheck{Finite non-negative decimal header?}
        HeaderCheck -->|Yes| Panel
        HeaderCheck -->|Missing or invalid| Unavailable[Show -- for service round trip]
        Unavailable --> Panel
    end
    subgraph telemetry[Shared telemetry path]
      direction TB
        Publish --> Manager[Metrics Manager POST /api/v1/metrics]
        Manager --> Prometheus[Prometheus field-expanded metrics for external consumers]
        Manager --> Proxy[Nginx proxies SSE /metrics/stream]
        Proxy --> Stream[MetricsProvider / useMetricsStream EventSource]
        Stream --> Redux[Redux latest metric samples]
    end
    subgraph platform[Continuous host-wide telemetry]
      direction TB
        Host[CPU, memory, GPU and NPU] --> Collectors[Telegraf and hardware collectors inside Metrics Manager]
        Collectors --> Manager
        Redux --> Dashboard[MetricsDashboard with useMetrics and local useMetricHistory]
        Dashboard --> Charts[Platform metrics section; no video FPS or pipeline latency]
    end
```

After a successful response is validated, the backend schedules a best-effort
publish to Metrics Manager. Publishing has a separate 2-second timeout and does
not delay or fail the conversion response. ASR produces
`voice_asr_service_round_trip_ms` tagged with requested `device` and `language`;
TTS produces `voice_tts_service_round_trip_ms` tagged with requested `device`
and `voice`. A missing device is tagged `service-default` and must not be read as
confirmation of the device the service actually used.

- **Request duration:** browser fetch start through complete response consumption
  and success checks, including upload, proxy handling, service work and download.
  It remains browser-local and is not published to Metrics Manager.
- **Service round trip:** backend adapter start through complete upstream body
  reception and local response construction; excludes browser transfer and
  subsequent route payload validation/context cleanup. Includes transport,
  queueing and service processing, not only model inference. This is the only
  Voice duration published to Metrics Manager.
- The intervals use independent monotonic clocks. No cross-machine timestamp
  subtraction or global last-request variable is needed.
- Published Voice metrics remain available through Metrics Manager's Prometheus
  and SSE interfaces, but the Voice performance panel shows only the current
  request-scoped timings returned with the conversion response.
- Platform charts are live system-wide telemetry, not a frozen snapshot of a
  conversion and not resource attribution to a particular STT/TTS request.
- Voice does not query the services' global `last_ms` or `/v1/model-info` and does
  not report model inference time, chunk or segment counts, effective device,
  end-to-end conversational latency or time to first audio.

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
  [performance panel](../../../ui/src/features/voice/VoiceMetrics.tsx).
- [Voice API and upstream adapter](../../../vippet/api/routes/voice.py).
- [Models page](../../../ui/src/pages/Models.tsx),
  [model installation hook](../../../ui/src/features/models/useModelInstall.ts),
  [model routes](../../../vippet/api/routes/models.py),
  [model manager](../../../vippet/managers/model_manager.py),
  [Whisper catalog entry](../../../vippet/models/voice-whisper-base.yaml),
  [SpeechT5 catalog entry](../../../vippet/models/voice-speecht5.yaml) and
  [catalog DB seeding](../../../vippet/db_seed.py).
- [Metrics stream](../../../ui/src/hooks/useMetricsStream.ts),
  [local chart history](../../../ui/src/hooks/useMetricHistory.ts) and
  [shared dashboard](../../../ui/src/features/metrics/MetricsDashboard.tsx).
- [Nginx routing](../../../ui/nginx.conf),
  [Compose configuration](../../../compose.yml) and
  [system telemetry architecture](./metrics/system-performance.md).
- [Voice user guide](../user-guide/voice-conversion.md),
  [backend regression tests](../../../vippet/tests/unit/api_tests/voice_test.py) and
  [browser regression tests](../../../ui/tests/voice.spec.ts).
