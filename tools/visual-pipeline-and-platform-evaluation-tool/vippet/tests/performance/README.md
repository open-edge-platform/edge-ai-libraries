# VIPPET Performance Benchmark Suite

Automated benchmarking of VIPPET pipelines on Intel platforms — CPU, GPU (Xe), and NPU.
Collects hardware KPIs per job and produces JSON, CSV, and HTML bar-chart reports.

## Prerequisites

- VIPPET running at `http://localhost:7860` with models downloaded
- Python dev venv set up (`make` from project root creates `.venv` automatically)

## Usage

```bash
make test-performance                    # default: CPU+GPU+NPU, 1 and 3 streams
make test-performance PERF_CONFIG=quick  # CPU+GPU only, 1 stream
make test-performance PERF_CONFIG=full   # all variants, 1/3/5/10 streams
```

Or call pytest directly for more control:

```bash
# Collect only (preview test matrix)
python -m pytest --collect-only vippet/tests/performance/

# Run a specific pipeline
python -m pytest --log-cli-level=INFO -m perf -k "object_detection" vippet/tests/performance/

# Generate JUnit XML for CI
python -m pytest -m perf --junitxml=results/perf.xml vippet/tests/performance/
```

## Configuration

Test parameters are controlled via YAML config files in `config/` and environment variables:

Set `benchmark.filters.skip_missing_models` in the selected YAML file to control
cases whose required models are not installed. It defaults to `true`, so affected
cases are reported as skipped with the missing model names. Set it to `false` to
schedule those cases and expose runtime failures, for example when validating
behavior on a host without the models.

| Env var                      | Default                           | Description                                                                                                                    |
|------------------------------|-----------------------------------|--------------------------------------------------------------------------------------------------------------------------------|
| `VIPPET_BASE_URL`            | `http://localhost/api/v1`         | VIPPET API endpoint                                                                                                            |
| `VIPPET_METRICS_URL`         | `http://localhost/metrics/stream` | Metrics endpoint (via nginx proxy)                                                                                             |
| `PERF_CONFIG`                | `default`                         | Config preset (`default`, `quick`, `full`)                                                                                     |
| `PERF_RESULTS_DIR`           | `./results`                       | Output directory for reports                                                                                                   |
| `PERF_METRICS_INTERVAL`      | `2.0`                             | HW sampling interval (seconds)                                                                                                 |
| `PERF_METRICS_TRIM_FRACTION` | `0.1`                             | Fraction of HW samples trimmed from each end before averaging (see [HW metric trimming](#hw-metric-trimming))                  |
| `PERF_ON_UNKNOWN_ID`         | `fail`                            | Unknown id in `pipelines` / `skip_pipelines` / `skip_variants` / `variants`: `fail` aborts the run, `warn` only logs a warning |

### HW metric trimming

`metrics.trim_fraction` (default `0.1`, override with `PERF_METRICS_TRIM_FRACTION`)
trims that fraction of time-ordered hardware samples from **both ends** before
computing each KPI's average — the same edge trimming VIPPET's own built-in
benchmark applies (`managers.benchmark_metrics.TRIM_FRACTION`), so warm-up and
wind-down samples don't drag the reported average down. `_min`/`_max` are
always computed from the **untrimmed** samples, so a real transient peak
still shows in the report.

With the default 2s sampling interval and a 30s run (~16 samples), a 10% trim
only drops one sample from each end — some startup idle may still be present
in the average. This matches VIPPET's built-in benchmark behavior today.

### Per-family KPI status (`ok` / `no_samples` / `idle`)

For each device family requested by a test case (derived from
`pipeline_case.device_family`, e.g. `GPU_NPU` → `GPU`, `NPU`), the HW monitor
classifies that family's activity across the run:

| Status       | Meaning                                                                                                                                   |
|--------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| `ok`         | At least one activity KPI (e.g. `npu_utilization`, falling back to `npu_frequency`/`npu_power` for NPU) was nonzero somewhere in the run. |
| `no_samples` | None of the family's KPI keys were ever reported by metrics-manager — the device is missing or the harness never got a successful poll.   |
| `idle`       | Samples exist for the family, but every activity value was zero for the entire run (hardware present but never dispatched work).          |

A requested family that isn't `ok` triggers both a `logger.warning` and a
`warnings.warn` (so it's visible in the pytest warnings summary), and shows up
in the reports instead of a blank cell:

- **CSV**: a `no_samples` family's `_avg`/`_max` cells show the literal
  `NO_SAMPLES` marker instead of an empty string. An `idle` family keeps its
  real (zero) numeric values — only the `kpi_warnings` column
  (e.g. `NPU:idle` or `NPU:no_samples;GPU:idle`) flags it.
- **HTML**: the per-pipeline table shows a small amber "no samples" / "idle"
  warning badge next to the affected family's utilization cell, and `NPU
  Freq` is labeled in **MHz** (matching metrics-manager's `npu_frequency`
  field).
- **JSON**: numeric KPI values stay numeric; the status lives in
  `hw_metrics.kpi_status` (per-family) and `hw_metrics.kpi_warnings`
  (semicolon-joined summary string).

## Layout

```text
conftest.py                 # pytest fixtures and parametrize hook
pytest.ini                  # markers and pythonpath
test_pipeline_performance.py  # test module
perf_helpers/
├── config.py               # env-var-driven constants
├── hw_monitor.py           # background HW metric sampler + per-family status
└── reporters.py            # JSON/CSV export + HTML report generation
config/
├── default.yaml            # CPU+GPU+NPU, 1 & 3 streams
├── quick.yaml              # CPU+GPU, 1 stream
└── full.yaml               # all variants, 1/3/5/10 streams
```

## Reports

After a run, results are saved to `results/bench_YYYYMMDD_HHMMSS/`:

- `.json` — structured results (all test cases + HW metrics)
- `.csv` — flat table for spreadsheet analysis
- `.html` — interactive Chart.js report with FPS, utilization, and power charts
