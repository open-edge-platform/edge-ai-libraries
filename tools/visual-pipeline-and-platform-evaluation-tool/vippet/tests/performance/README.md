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

# Extra CLI flags via PERF_ARGS
make test-performance PERF_ARGS="--dry-run"
make test-performance PERF_CONFIG=quick PERF_ARGS="--streams 1,5 --pipelines object-detection"
```

`make test-performance` delegates to the CLI below.

### CLI

Run from the project root. `PYTHONPATH` must include `vippet/tests/performance`:

```bash
export PYTHONPATH=vippet/tests/performance

python -m perf_helpers.cli --help
python -m perf_helpers.cli --config quick --base-url http://10.0.0.5/api/v1
python -m perf_helpers.cli --variants cpu,gpu --streams 1,3,5 --results-dir /tmp/perf
python -m perf_helpers.cli --config ./my-config.yaml

# Arguments after `--` go to pytest unchanged
python -m perf_helpers.cli --streams 1 -- -k object_detection --junitxml=results/perf.xml
```

The CLI builds the effective configuration and runs `python -m pytest -m perf` in a
subprocess. It passes `vippet/tests/performance` as the test path, unless an argument
after `--` already selects a `.py` file, directory or node id inside it. Option values
such as `--junitxml results/perf.xml` never replace the test path.

The resolved config is passed through a temporary YAML file that only the current
user can read (`PERF_CONFIG_FILE`), and the file is deleted afterwards. The CLI
exits with pytest's exit code. If the config or a flag is invalid, it exits with `2`.

#### Dry run

`--dry-run` checks that ViPPET is up and reads `/pipelines`, `/devices` and
`/models`. It never submits a job. It prints:

- the effective setting of every key and where each value came from (`default`,
  `yaml`, `env`, `cli`)
- the **Matrix**: pipeline × variant × streams, with the pytest test id
- **Excluded** pipelines/variants, with a reason:

  | Reason               | Meaning                                                                 |
  |----------------------|-------------------------------------------------------------------------|
  | `pipeline_filter`    | Pipeline not listed in `benchmark.pipelines`                            |
  | `skip_pipelines`     | Pipeline listed in `benchmark.filters.skip_pipelines`                   |
  | `skip_variants`      | Variant listed in `benchmark.filters.skip_variants`                     |
  | `variant_filter`     | Variant uses a device family not in `benchmark.variants`                |
  | `unsupported_family` | Unknown device family, or a family the host does not report             |
  | `malformed`          | Pipeline/variant entry from the API has no id or name                   |

- **Skipped at run time: missing_models**: runs that are in the matrix but that pytest
  will skip because their models are not installed, with the model names

```text
Matrix: 4 run(s) = pipeline x variant x streams [1, 3]
pipeline          variant  streams  test id
----------------  -------  -------  -----------------------
object-detection  CPU      1        object_detection_cpu_x1
...
Excluded: 2 pipeline/variant(s)
pipeline          variant  reason              detail
----------------  -------  ------------------  ------------------------------------------
object-detection  NPU      unsupported_family  host does not report ['NPU']
smart-parking     (all)    skip_pipelines      listed in benchmark.filters.skip_pipelines
```

If ViPPET cannot be reached, `--dry-run` exits with `2`. It exits with `0` in every
other case.

`--collect-only` lists the collected tests, but it does not say why a case was left out.

#### Report only

`--report-only` is reserved for rebuilding reports from existing results without
running any jobs. It is not implemented yet and exits with `3`.

### Direct pytest

You can still call pytest directly. It reads the same YAML and env vars; there are no
CLI flags in this mode:

```bash
# Collect only (preview test matrix)
python -m pytest --collect-only vippet/tests/performance/

# Run a specific pipeline
python -m pytest --log-cli-level=INFO -m perf -k "object_detection" vippet/tests/performance/

# Generate JUnit XML for CI
python -m pytest -m perf --junitxml=results/perf.xml vippet/tests/performance/
```

## Configuration

Settings are combined in this order. Each layer overrides the one before it:

```text
built-in defaults -> YAML config -> environment variables -> CLI flags
```

The YAML file is chosen in this order: `--config`, then `PERF_CONFIG_FILE` (a path),
then `PERF_CONFIG` (a preset name in `config/` or a path), then `default`. An unknown
preset, a missing file, an unknown YAML key or an invalid value stops the run with an
error. Older versions silently fell back to `default.yaml` instead.

Every YAML key has a CLI flag:

| Flag                         | YAML key                                  | Env var                           |
|------------------------------|-------------------------------------------|-----------------------------------|
| `--config`                   | (selects the YAML file)                   | `PERF_CONFIG_FILE`, `PERF_CONFIG` |
| `--base-url`                 | `vippet.base_url`                         | `VIPPET_BASE_URL`                 |
| `--timeout`                  | `vippet.timeout`                          |                                   |
| `--readiness-timeout`        | `vippet.readiness_timeout_seconds`        |                                   |
| `--poll-interval`            | `vippet.poll_interval`                    | `VIPPET_JOB_POLL_INTERVAL`        |
| `--max-job-duration`         | `vippet.max_job_duration`                 | `VIPPET_JOB_TIMEOUT_SECONDS`      |
| `--pipelines`                | `benchmark.pipelines`                     |                                   |
| `--variants`                 | `benchmark.variants`                      |                                   |
| `--streams`                  | `benchmark.stream_counts`                 |                                   |
| `--max-retries`              | `benchmark.execution.max_retries`         |                                   |
| `--retry-delay`              | `benchmark.execution.retry_delay_seconds` |                                   |
| `--output-mode`              | `benchmark.execution.output_mode`         |                                   |
| `--max-runtime`              | `benchmark.execution.max_runtime`         |                                   |
| `--skip-pipelines`           | `benchmark.filters.skip_pipelines`        |                                   |
| `--skip-variants`            | `benchmark.filters.skip_variants`         |                                   |
| `--[no-]skip-missing-models` | `benchmark.filters.skip_missing_models`   |                                   |
| `--metrics-url`              | `metrics.metrics_url`                     | `VIPPET_METRICS_URL`              |
| `--metrics-interval`         | `metrics.sample_interval_seconds`         | `PERF_METRICS_INTERVAL`           |
| `--results-dir`              | `results.output_dir`                      | `PERF_RESULTS_DIR`                |
| `--formats`                  | `results.formats`                         |                                   |
| `--[no-]latest-link`         | `results.create_latest_link`              |                                   |

Notes:

- List flags take comma-separated values, e.g. `--streams 1,3,5` or `--pipelines a,b`.
  `--pipelines '*'` selects all pipelines. Pass `--skip-pipelines ''` to clear a list.
- `--variants` lists the allowed device **families**. A variant runs only if every
  family it uses is allowed: `GPU_NPU` needs both `gpu` and `npu`. So listing
  `gpu_npu` is redundant once `gpu` and `npu` are listed (as in `full.yaml`).
- `--no-skip-missing-models` lets pipelines with missing models run anyway
  (and fail at runtime) instead of being skipped with the missing-model
  reason shown.
- The CLI always passes `vippet/tests/performance` to pytest, so arguments after
  `--` can't move collection elsewhere. Paths or node ids after `--` don't narrow
  the run; use `--pipelines`, `--variants`, `--streams` or `-k` instead.

Environment variable defaults:

| Env var                      | Default                           | Description                                                                                                                    |
|------------------------------|-----------------------------------|--------------------------------------------------------------------------------------------------------------------------------|
| `VIPPET_BASE_URL`            | `http://localhost/api/v1`         | VIPPET API endpoint                                                                                                            |
| `VIPPET_METRICS_URL`         | `http://localhost/metrics/stream` | Metrics endpoint (via nginx proxy)                                                                                             |
| `VIPPET_JOB_POLL_INTERVAL`   | `2.0`                             | Job status polling interval (seconds)                                                                                          |
| `VIPPET_JOB_TIMEOUT_SECONDS` | `600`                             | Max wait for a job, whole seconds                                                                                              |
| `PERF_CONFIG`                | `default`                         | Config preset (`default`, `quick`, `full`)                                                                                     |
| `PERF_CONFIG_FILE`           | (unset)                           | Explicit YAML path; wins over `PERF_CONFIG`                                                                                    |
| `PERF_RESULTS_DIR`           | `./results`                       | Output directory for reports                                                                                                   |
| `PERF_METRICS_INTERVAL`      | `2.0`                             | HW sampling interval (seconds)                                                                                                 |
| `PERF_ON_UNKNOWN_ID`         | `fail`                            | Unknown id in `pipelines` / `skip_pipelines` / `skip_variants` / `variants`: `fail` aborts the run, `warn` only logs a warning |

`VIPPET_JOB_POLL_INTERVAL` and `VIPPET_JOB_TIMEOUT_SECONDS` are also read by the
functional-test helpers. The CLI and direct pytest both resolve them the same way.
Numbers must be finite (`nan` and `inf` are rejected). With direct pytest, an invalid
config also prints a one-line error and exits with `2`.

## Layout

```text
conftest.py                 # pytest fixtures and parametrize hook
pytest.ini                  # markers and pythonpath
test_pipeline_performance.py  # test module
perf_helpers/
├── cli.py                  # CLI entry point (python -m perf_helpers.cli)
├── settings.py             # setting specs + defaults -> YAML -> env -> CLI resolver
├── config.py               # module constants derived from settings.py
├── matrix.py               # pure pipeline x variant x streams builder with exclusion reasons
├── discovery.py            # read-only ViPPET queries feeding matrix.py
├── preflight.py            # ViPPET health/readiness check
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
