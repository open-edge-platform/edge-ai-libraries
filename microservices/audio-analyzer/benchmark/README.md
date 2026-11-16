# Audio Analyzer Benchmarking

This guide covers how the Audio Analyzer microservice is benchmarked: what is measured, how it
is measured, how to run the scripts, and the results so far.

## Contents

- [Benchmarking overview](#benchmarking-overview)
- [Scope](#scope)
- [Strategy and approach](#strategy-and-approach)
- [APIs and payloads](#apis-and-payloads)
- [KPIs and how they are measured](#kpis-and-how-they-are-measured)
- [Timing diagrams](#timing-diagrams)
- [Usage](#usage)
- [Outputs](#outputs)
- [Interpreting results and limitations](#interpreting-results-and-limitations)

---

## Benchmarking overview

The benchmark suite is in this folder. It contains two load generators and a shared
resource monitor:

| File | Purpose |
|---|---|
| [bench_audio_analyzer.py](bench_audio_analyzer.py) | **Batch streaming (SSE)** benchmark. Uploads a whole audio file and consumes the OpenAI-compatible SSE transcript stream. |
| [bench_realtime.py](bench_realtime.py) | **Realtime (WebSocket)** benchmark. Acts as a live speaker that streams PCM16 audio at real-time pace, and measures per-utterance latency after the speaker stops talking. |
| [resource_utilization.py](resource_utilization.py) | Starts the Metrics Manager container, samples host CPU, GPU, NPU, memory, and temperature every 1 s, and writes a summary CSV and a plot. |
| [requirements.txt](requirements.txt) | Client dependencies: `aiohttp`, `tokenizers`, `requests`, `matplotlib`. `bench_realtime.py` also needs `numpy`. |
| `data/` | Input audio. `data/*` is used by the SSE benchmark and `data/realtime/*` by the realtime benchmark. |
| `results/` | One folder per run (raw CSVs, transcripts, `summary.json`, and resource logs). |

Both scripts are client-side and black-box. They talk to a running service over HTTP or
WebSocket, timestamp protocol events with `time.perf_counter()`, and aggregate the
measurements into percentile statistics (mean, min, max, p50, p90, p99).

---

## Scope

### In scope

| Area | SSE benchmark | Realtime benchmark |
|---|---|---|
| Endpoint | `POST /v1/audio/transcriptions` with `stream=true` | `WS /v1/realtime?intent=transcription` |
| Protocol | HTTP multipart upload, then `text/event-stream` | WebSocket, JSON events, base64 PCM16 |
| Use case | File or batch transcription with progressive output | Live captioning or a voice agent (speech-end → final text) |
| Load model | Closed loop with N concurrent workers, swept over `--concurrency` | One live stream per input file, run in sequence |
| Default input | `data/philosophy_10_russell_128kb.mp3` (~900 s, MP3) | `data/realtime/1272-141231.wav` (239.8 s, 16 kHz mono, LibriSpeech dev-clean) |
| Metadata | `GET /v1/model-info` (provider, model, device, weight format) | Same, plus server VAD settings from `transcription_session.created` |
| System metrics | CPU, GPU, NPU, memory, and temperature during measured runs only | Same |

### Out of scope

- Non-streaming transcription (`stream=false`), the NDJSON endpoint
  `/v1/audio/transcriptions/stream`, and the VSS `/transcriptions` API.
- Sentiment analysis and session-summary endpoints.
- Accuracy (WER). Transcripts are saved for offline comparison, but no WER is computed.
- Server-internal profiling. All timings are taken on the client.
- Model, device, and diarization selection. These are server deployment settings
  (`config.yaml`). Change them by redeploying, then rerun the benchmark.

---

## Strategy and approach

1. **Discover the deployment.** Each script reads `GET /v1/model-info` and records the served
   ASR provider, model, device, and weight format in `summary.json`, so every result is tied to
   a known configuration. The request always uses the OpenAI alias `model=whisper-1`.
2. **Prepare inputs before any timing.**
   - SSE: each file in `data/` is read into memory once. `ffprobe` records its duration, codec,
     sample rate, channels, and bit rate.
   - Realtime: each input is converted once to the socket's wire format (PCM16 LE, mono,
     16 kHz) with FFmpeg. A 16 kHz mono PCM16 WAV is used as-is. The converted audio is then
     split into `--frame-ms` frames and base64-encoded.
3. **Warm up (not recorded).** The SSE script sends `--warmup` full requests. The realtime
   script sends `--warmup` short streams (`--warmup-sec` of audio) in burst mode. Warmup loads
   and compiles the model, and runs before resource monitoring starts.
4. **Start resource monitoring.** The Metrics Manager container is started, and Prometheus
   metrics are polled every 1 s, so the monitoring window covers only measured traffic.
5. **Generate load.**
   - SSE: a **closed loop**. `concurrency` async workers each send a request, wait for
     `[DONE]`, then send the next, until `--num-requests` requests are done. This repeats for
     each value in the `--concurrency` sweep, and the start and end epochs of each point are
     recorded.
   - Realtime: an **open-loop live speaker**. Frames are sent on a fixed schedule
     (`t0 + (i+1)·frame_ms / speed`), independent of server responses, as a microphone would.
6. **Attribute latency.**
   - SSE: the request is split into the client-observable phases upload, decode (time to
     first chunk), and inference (streaming).
   - Realtime: the client **replays the server's deterministic energy VAD** (30 ms frames,
     RMS ≥ threshold, commit after `silence_duration_ms`) on the same audio. For every server
     commit it then knows where speech ended on the audio timeline, and so when that audio
     frame was sent. A predicted commit count that differs from the server's is reported as
     `commit_mismatch`.
7. **Validate and aggregate.** A request or stream fails on an HTTP error, a timeout, an empty
   stream, a server `error` event, or an impossible ordering (first chunk before the upload
   finished). Failed requests are kept in the raw CSVs and excluded from the statistics.
8. **Persist.** Results go to raw CSVs, `transcripts.txt`, `summary.json`, and
   `perf_tool_logs/` (metrics stream, summary CSV, and utilization plot).

---

## APIs and payloads

### SSE: `POST /v1/audio/transcriptions` (stream=true)

Request (`multipart/form-data`):

| Field | Value |
|---|---|
| `file` | Audio bytes, MIME type guessed from the extension |
| `model` | `whisper-1` (alias; the served model is set on the server) |
| `language` | `en` |
| `response_format` | `json` |
| `stream` | `true` |

Response (`text/event-stream`), with one delta per server-side audio chunk:

```text
data: {"type": "transcript.text.delta", "delta": "First chunk text ..."}
data: {"type": "transcript.text.delta", "delta": "Second chunk text ..."}
data: {"type": "transcript.text.done", "text": "<full transcript>", "language": "en", "duration": 900.1}
data: [DONE]
```

### Realtime: `WS /v1/realtime?intent=transcription&language=en`

| Direction | Event | Payload / purpose |
|---|---|---|
| S → C | `transcription_session.created` | Session ID and default `turn_detection` (`server_vad`: `threshold`, `silence_duration_ms`, `prefix_padding_ms`) |
| C → S | `session.update` | `sample_rate: 16000`, `input_audio_format: pcm16`, the server's own VAD settings, and optionally `diarization: true/false` |
| S → C | `transcription_session.updated` | Acknowledges the update |
| C → S | `input_audio_buffer.append` | `{"audio": "<base64 PCM16 frame>"}`, one per `--frame-ms` (default 100 ms = 3,200 bytes) |
| S → C | `input_audio_buffer.committed` | VAD cut an utterance (`item_id`, `reason`) |
| S → C | `conversation.item.input_audio_transcription.completed` | Transcript for `item_id` (the service returns the **accumulated** session text) |
| S → C | `error` | Failure for an utterance or the session |
| C → S | `session.close` | Flushes and commits any remaining buffer, then closes |

### Auxiliary

- `GET /v1/model-info` → `provider`, `model`, `device`, `weight_format`.
- Metrics Manager (`intel/metrics-manager:2026.2.0`): health `:9091/health`, Prometheus
  `:9274/metrics`. The series used are `cpu_usage_user`, `gpu_engine_usage*`,
  `npu_utilization`, `mem_used_percent`, and `temp_temp`.

---

## KPIs and how they are measured

### SSE KPIs (per request)

All values are measured from the same `t0`, taken just before the request is sent.

| KPI | Measurement | Meaning |
|---|---|---|
| `upload_time_s` | `t0` → the wrapped multipart payload's `write()` returns (closing boundary written) | Client upload time. This is not a server acknowledgement. |
| `ttft_s` | `t0` → first non-empty `transcript.text.delta` | Time to first transcript. The responsiveness the user experiences. |
| `decode_time_s` | `ttft_s − upload_time_s` | Server file save, FFmpeg decode and chunking, and ASR of the first chunk |
| `itl_s` | Gap between consecutive deltas | Time per audio chunk (inter-chunk latency). In the CSV it is the mean for one request. In the summary, percentiles are taken over **all** gaps. |
| `inference_time_s` | `e2e_latency_s − ttft_s` | Streaming phase after the first chunk |
| `e2e_latency_s` | `t0` → `[DONE]` | Total request latency |
| `output_tokens` | Final text tokenized with the **served model's** tokenizer | Output volume. The tokenizer comes from `--tokenizer`, then the service container (`docker exec`), then the HF `openai/<model>`. |
| `total_chunks` | Number of non-empty deltas | Should be constant for a given file |
| `wall_time_s`, `success`, `errors` | Per concurrency point | Throughput and reliability (requests/s = `success / wall_time_s`) |

### Realtime KPIs (per utterance and per stream)

| KPI | Level | Measurement | Meaning |
|---|---|---|---|
| `eos_to_final_s` | utterance | Send time of the frame holding the last speech sample → `completed` received | **Latency a live user feels** after they stop talking |
| `vad_delay_s` | utterance | Same start → `committed` received | About `silence_duration_ms`, plus any backlog |
| `asr_s` | utterance | `committed` → `completed` | ASR time, plus any wait for the shared model |
| `rtf` | utterance | `asr_s / audio_dur_s` | Real-time factor. Below 1 means the server keeps up. Sustainable streams ≈ `1 / rtf`. |
| `drain_s` | stream | `session.close` sent → last server event | Tail latency to flush |
| `wall_s` | stream | First frame → socket closed | About the audio duration at `--speed 1` |
| `utterances`, `empty_utterances`, `commit_mismatch_streams` | run | Event counts | VAD and transcription health |

### System KPIs (per run)

Average, minimum, and maximum of CPU user %, GPU engine %, NPU %, memory %, and temperature
(°C), sampled every 1 s over the measured window. Use the `start_epoch`/`end_epoch` of each
point to match peaks to a concurrency level.

---

## Timing diagrams

### SSE request

```text
t0 ── upload ──┬──── decode ────┬──────── inference (deltas, itl) ────────┐
          upload_time_s       ttft_s                                 e2e_latency_s
```

### Realtime utterance

```text
speech end ── VAD silence wait ──> committed ── ASR (+ queue) ──> completed
|<─────────── vad_delay_s ───────>|<──────── asr_s ────────────>|
|<───────────────────────── eos_to_final_s ────────────────────>|
```

---

## Usage

### Prerequisites

- A running Audio Analyzer service (default `http://localhost:8010`).
- Python 3.9 or later: `pip install -r requirements.txt numpy`.
- `ffmpeg`/`ffprobe` on `PATH`. The realtime benchmark needs `ffmpeg` for non-PCM inputs.
- Docker CLI access, to read the tokenizer from the service container and to run the Metrics
  Manager (`--privileged`, host ports `9091` and `9274` free). Docker is not needed with
  `--no-resource-util` and `--tokenizer`.

### SSE benchmark: `bench_audio_analyzer.py`

```bash
cd benchmark

# Smoke test
python3 bench_audio_analyzer.py --concurrency 1 --num-requests 1 --warmup 0 --no-resource-util

# Concurrency sweep with resource utilization
python3 bench_audio_analyzer.py --concurrency 1,2,4 --num-requests 4

# Pin the client to one core so it does not compete with the service
taskset -c 0 python3 bench_audio_analyzer.py --concurrency 1,2,4 --num-requests 4
```

| Argument | Default | Description |
|---|---|---|
| `--base-url` | `http://localhost:8010` | Service URL |
| `--concurrency` | `1` | Comma-separated sweep, for example `1,2,4` |
| `--num-requests` | `1` | Measured requests per concurrency point |
| `--warmup` | `1` | Unrecorded warmup requests (`0` skips warmup) |
| `--timeout` | `1200` | Per-request timeout (s) |
| `--tokenizer` | served model | `tokenizer.json` path, directory, or HF ID |
| `--out-dir` | `results/` | Root folder for results. Each run writes to `<out-dir>/<YYYYmmdd-HHMMSS>/`. |
| `--resource-util` / `--no-resource-util` | enabled | Turns system metrics collection on or off |
| `--metrics-image` | `intel/metrics-manager:2026.2.0` | Metrics Manager image |

### Realtime benchmark: `bench_realtime.py`

```bash
cd benchmark

# Real-time pace over every file in data/realtime/
python3 bench_realtime.py

# Your own recording (any FFmpeg-readable format); keep the converted PCM
python3 bench_realtime.py --input ~/recordings/call.mp3 --save-converted

# Burst mode (no pacing): measures throughput (asr_s, rtf), not live latency
python3 bench_realtime.py --speed 0 --no-resource-util
```

| Argument | Default | Description |
|---|---|---|
| `--base-url` | `http://localhost:8010` | Service URL (the `ws://` or `wss://` URL is derived from it) |
| `--input` | — | One or more audio or video files or folders |
| `--data-dir` | `data/realtime/` | Default input folder when `--input` is not given |
| `--save-converted` | off | Write the PCM that was sent to `<run>/converted/<name>.realtime.wav` |
| `--speed` | `1.0` | `1.0` = real time, `2.0` = 2× faster, `0` = burst |
| `--frame-ms` | `100` | Audio per `append` message (≥ 10) |
| `--tail-silence-ms` | `1000` | Silence appended so the last utterance is committed |
| `--language` | `en` | `language` query parameter (`''` for auto-detection) |
| `--diarization` | server config | `on`/`off` per-session override |
| `--warmup` / `--warmup-sec` | `1` / `20` | Unrecorded burst-mode warmup streams and their length |
| `--timeout` | `1800` | Per-stream timeout (s) |
| `--out-dir`, `--resource-util`, `--metrics-image` | — | Same as the SSE benchmark |

The VAD threshold, `silence_duration_ms`, and `prefix_padding_ms` are read from the server and
replayed. They cannot be set from the command line.

Both scripts run in this order: inputs → `/v1/model-info` → warmup → start monitor →
measured runs → stop monitor → plot.

---

## Outputs

```text
results/<YYYYmmdd-HHMMSS>[-realtime]/
├── raw_transcribe_sse.csv        # SSE: one row per request
├── raw_realtime_utterances.csv   # realtime: one row per server commit
├── raw_realtime_streams.csv      # realtime: one row per stream
├── transcripts.txt               # transcript per request or stream
├── summary.json                  # server_info, inputs, run_args, points[] (distributions), resource window
└── perf_tool_logs/
    ├── metrics_stream.log
    ├── metrics_summary.csv       # Avg/Min/Max per series
    └── resource_utilization.png
```

The console prints p50 values for each concurrency point (SSE) or for the run (realtime:
`eos_p50`, `eos_p90`, `asr_p50`, `rtf_p50`, and mean `drain`).


## Interpreting results and limitations

- Use `--speed 1` for live latency. In burst mode, `eos_to_final_s` is mostly queueing time,
  and only `asr_s` and `rtf` are meaningful.
- `eos_to_final_s` includes up to one frame (`--frame-ms`) of client capture delay.
- SSE `decode_time_s` cannot separate FFmpeg decoding from ASR of the first chunk.
- `upload_time_s` is the time the client finished writing, not a server acknowledgement.
- For stable numbers, repeat each configuration (for example, 3 runs) and compare medians.
  Pin the client with `taskset` when it shares a host with the service.
- Each SSE request creates a server session, and its files remain under the service's
  `storage/` folder.
- Diarization, model, device, and weight format are not request parameters (except the
  per-session realtime `--diarization` override). Record them in the result folder name, as in
  the runs above.
