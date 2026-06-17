# System Performance

This article describes how ViPPET collects and reports **host-level** system
telemetry — CPU, memory, GPU and NPU utilization — independently of any
particular pipeline run.

While [Pipeline Performance](./pipeline-performance.md) covers per-job metrics
(FPS, latency) produced by the GStreamer pipeline itself, *system performance*
reflects the state of the machine on which ViPPET is running. It is collected
continuously, regardless of whether any job is active.

## Components

| Component                                  | Role                                                                                                                                       |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `telegraf` (embedded in `metrics-manager`) | Collects host metrics: CPU usage, memory, CPU frequency, plus GPU/NPU metrics via custom collectors.                                       |
| `metrics-manager`                          | Scrapes the Telegraf Prometheus endpoint, normalizes samples, retains a short rolling window and re-publishes them to UI clients over SSE. |
| `vippet-ui`                                | Subscribes to the SSE stream and renders the dashboard charts.                                                                             |

The Telegraf configuration shipped with ViPPET lives in
[`vippet-telegraf.conf`](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/tools/visual-pipeline-and-platform-evaluation-tool/vippet-telegraf.conf)
and is mounted read-only into the `metrics-manager` container.

## Data flow

```text
Host (CPU / Memory / GPU / NPU)
   │
   ▼
telegraf  (inputs: cpu, mem, exec/execd for GPU & NPU via custom collectors)
   │  Prometheus endpoint :9273
   ▼
metrics-manager  (scrape + rolling window, retention 300 s)
   │  SSE  /metrics/stream    (port 9090)
   ▼
nginx (vippet-ui)  → proxies /metrics/stream to metrics-manager
   │
   ▼
Browser (EventSource) → Redux store → System dashboard charts
```

1. **Telegraf** samples the host every second (`interval = "1s"`) and exposes
   the readings as Prometheus metrics on port `9273`.
2. **metrics-manager** scrapes that endpoint, keeps a 300-second rolling
   window in memory and pushes new samples to every connected SSE client on
   `/metrics/stream` (port `9090`).
3. **vippet-ui** opens a single `EventSource` connection (proxied by nginx)
   and dispatches incoming samples into the Redux store, which feeds the
   system-performance charts on the dashboard.

System metrics are emitted independently of pipeline runs, so the dashboard
shows host utilization even when no job is active and continues recording
during the entire session.
