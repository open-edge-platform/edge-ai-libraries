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

| Env var                 | Default                          | Description                               |
| ----------------------- | -------------------------------- | ----------------------------------------- |
| `VIPPET_BASE_URL`       | `http://localhost/api/v1`        | VIPPET API endpoint                       |
| `VIPPET_METRICS_URL`    | `http://localhost/metrics/stream` | Metrics endpoint (via nginx proxy)        |
| `PERF_CONFIG`           | `default`                        | Config preset (`default`, `quick`, `full`) |
| `PERF_RESULTS_DIR`      | `./results`                      | Output directory for reports              |
| `PERF_METRICS_INTERVAL` | `2.0`                            | HW sampling interval (seconds)            |

## Layout

```text
conftest.py                 # pytest fixtures and parametrize hook
pytest.ini                  # markers and pythonpath
test_pipeline_performance.py  # test module
perf_helpers/
├── config.py               # env-var-driven constants
├── hw_monitor.py           # background HW metric sampler
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
