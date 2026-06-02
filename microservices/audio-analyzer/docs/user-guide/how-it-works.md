# How It Works

This page describes the architecture and internal flow of an audio request
through the microservice.

## Architecture

At a high level, the Audio Analyzer is a FastAPI service that accepts an
audio upload, splits it into chunks with FFmpeg, runs each chunk through an
ASR backend, and (optionally) runs a sentiment model in parallel. Results
are aggregated per session and returned either as a single JSON response or
as an NDJSON event stream.

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'fontFamily': '"IntelOne Display", "Intel Clear", "Inter", "Segoe UI", Arial, sans-serif',
    'fontSize': '14px',
    'primaryColor': '#0068B5',
    'primaryTextColor': '#FFFFFF',
    'primaryBorderColor': '#00377C',
    'lineColor': '#00377C',
    'secondaryColor': '#EEF3F8',
    'tertiaryColor': '#F7F8FA',
    'background': '#FFFFFF',
    'mainBkg': '#FFFFFF',
    'clusterBkg': '#F7F8FA',
    'clusterBorder': '#0068B5',
    'edgeLabelBackground': '#FFFFFF',
    'noteBkgColor': '#F7F8FA',
    'noteTextColor': '#3A3A3A'
  }
}}%%
flowchart LR
    Client([Client])

    subgraph Service["Audio Analyzer (FastAPI, :8010)"]
        API["API Layer<br/>(transcription / health / devices)"]
        Pipeline["Pipeline Orchestrator<br/>(pipeline.py)"]
        Pre["Preprocessing<br/>(FFmpeg: decode, chunk, denoise)"]
        ASR["ASR Backend<br/>(openai | openvino | whispercpp)"]
        Sent["Sentiment Backend<br/>(openvino | pytorch)"]
        Session[("Session Store<br/>storage/&lt;session_id&gt;/")]
    end

    Models[("Model Cache<br/>models/")]
    Device{{"Inference Device<br/>CPU / GPU"}}

    Client -- "POST /v1/audio/transcriptions{,/stream}" --> API
    API --> Pipeline
    Pipeline --> Pre
    Pre --> ASR
    Pre --> Sent
    ASR --> Device
    Sent --> Device
    ASR --> Pipeline
    Sent --> Pipeline
    Pipeline <--> Session
    ASR -. loads .-> Models
    Sent -. loads .-> Models
    Pipeline -- "JSON response / NDJSON events<br/>X-Session-ID header" --> Client

    classDef client fill:#FFFFFF,stroke:#0068B5,stroke-width:2px,color:#3A3A3A;
    classDef core fill:#0068B5,stroke:#00377C,stroke-width:1.5px,color:#FFFFFF;
    classDef backend fill:#00A3F4,stroke:#00377C,stroke-width:1.5px,color:#FFFFFF;
    classDef store fill:#6C6C6C,stroke:#0068B5,stroke-width:1.5px,color:#FFFFFF;
    classDef device fill:#00C7FD,stroke:#00377C,stroke-width:1.5px,color:#3A3A3A;

    class Client client;
    class API,Pipeline,Pre core;
    class ASR,Sent backend;
    class Session,Models store;
    class Device device;

    style Service fill:#F7F8FA,stroke:#0068B5,stroke-width:1.5px,color:#3A3A3A;
```

**Key planes:**

- **API layer** — request validation, session header handling, response
  shaping (single JSON vs. streaming NDJSON).
- **Pipeline orchestrator** — drives preprocessing, ASR, and sentiment;
  aggregates per-chunk results into a session-level summary.
- **Backends** — pluggable ASR and sentiment implementations selected via
  config; each backend handles its own model loading and device placement.
- **Session store** — per-session directory holding chunk files and
  metadata; enables multi-upload continuation via `session_id`.

## Request Flow

1. **Upload** — A client sends an audio file to either
   `POST /v1/audio/transcriptions` (single response) or
   `POST /v1/audio/transcriptions/stream` (NDJSON event stream).
2. **Session resolution** — If `session_id` is supplied, the service reuses
   the existing session directory under `storage/<session_id>/`. Otherwise, it
   creates a new session and returns the id in the `X-Session-ID` response
   header.
3. **Preprocessing** — FFmpeg decodes the upload and produces audio chunks
   under the configured `audio_preprocessing.chunk_dir`. Chunk size, silence
   detection, and optional denoising are controlled by the
   `audio_preprocessing` config section.
4. **ASR inference** — Each chunk is transcribed by the configured ASR
   backend (`openai` or `openvino`) on the configured device (typically
   `CPU`, optionally `GPU` for supported OpenVINO paths).
5. **Sentiment (optional)** — When `sentiment.enabled` is true, the
   service runs the configured sentiment model (`openvino` or `pytorch`) and
   aggregates a session-level summary.
6. **Response** — The non-streaming endpoint returns a final response object;
   the streaming endpoint emits `transcription.chunk` events as each chunk
   completes and a final `transcription.completed` event.
7. **Cleanup** — If `pipeline.delete_chunks_after_use` is true, temporary
   chunk files are removed after processing. Session metadata remains under
   `storage/<session_id>/`.

## Components

- `api/` — FastAPI routers for transcription, health, and device listing.
- `pipeline.py` — Orchestrates preprocessing, ASR, and sentiment.
- `components/` — Backend implementations for ASR and sentiment providers.
- `utils/` — Audio utilities, config loading, and session helpers.
- `dto/` — Request and response data models.

## Configuration Surface

All runtime behavior is driven by `config.yaml`, shared by both standalone
and container runs, with targeted overrides via `AUDIO_ANALYZER__...`
environment variables. See the [Configuration Guide](./get-started/configuration.md) for the
full list of fields.
