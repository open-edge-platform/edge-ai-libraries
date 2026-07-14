# VIPPET Benchmark Suite

Automated benchmarking of VIPPET pipelines on Intel Panther Lake — CPU, GPU (Xe), and NPU.
Collects hardware KPIs per job and produces JSON, CSV, and HTML bar-chart reports.

## Prerequisites

- VIPPET running at `http://localhost:7860` with models downloaded (see below)
- Python 3.9+ with `pip3 install -r requirements.txt`

## Usage

```bash
./run.sh                   # all pipelines, CPU+GPU+NPU, 1 and 3 streams (~30–60 min)
./run.sh --quick           # CPU+GPU only, 1 and 3 streams
./run.sh --dry-run         # preview test matrix without running
./run.sh --config config/full.yaml          # 1/3/5/10 streams, all variants
./run.sh --pipelines motion-detection       # single pipeline
./run.sh --variants cpu,gpu --streams 1,3,5
./run.sh --report-only results/latest/*.json  # regenerate HTML from existing result
```

`run.sh` checks dependencies, waits for VIPPET to be ready, runs the benchmark, and generates an HTML
report alongside the JSON/CSV.

## Layout

```text
run.sh                  # entry point
requirements.txt
config/
  default.yaml          # all pipelines, cpu+gpu+npu, streams 1,3  (~30–60 min)
  quick.yaml            # cpu+gpu only,  streams 1,3               (~15–30 min)
  full.yaml             # all pipelines, all variants, streams 1,3,5,10  (~2–3 h)
scripts/
  benchmark.py          # CLI
  generate_report.py    # HTML report
src/
  orchestrator.py       # test matrix, job submission, retry
  vippet_client.py      # VIPPET REST API client
  hw_monitor.py         # per-job HW KPI sampler
  reporters.py          # JSON/CSV export
```

## Hardware KPIs

Sampled per job by a background thread via VIPPET metrics-manager — not system-wide averages.

| Metric                                          | Source                                       |
|-------------------------------------------------|----------------------------------------------|
| GPU engine utilisation (render, video, compute) | `metrics-manager` (`gpu_engine_usage_usage`) |
| GPU frequency                                   | `metrics-manager` (`gpu_frequency`)          |
| GPU power, package power                        | `metrics-manager` (`gpu_power`)              |
| NPU utilisation, frequency, power, temperature  | `metrics-manager` Prometheus                 |
| CPU utilisation, frequency, system memory       | `metrics-manager` Prometheus                 |
| CPU temperature                                 | `metrics-manager` (`temp_temp`)              |

## Results

```text
results/
├── bench_YYYYMMDD_HHMMSS/
│   ├── *.json    full results
│   ├── *.csv     flat table, one row per test
│   └── *.html    bar-chart report (Chart.js)
└── latest/       symlink to most recent run
```
