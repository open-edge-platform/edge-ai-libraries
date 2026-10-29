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
make test-performance PERF_ARGS="--report-only"   # rebuild HTML from results/latest

# Verbose: stream INFO logs live (arguments after `--` go to pytest).
# The full INFO log is always saved next to the reports; see "Reports" below.
make test-performance PERF_ARGS="-- --log-cli-level=INFO"
```

`make test-performance` delegates to the CLI below and prints the same console output
(see [Console output](#console-output)).

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

The CLI passes its `--config`, setting flags and `--allow-matrix-drift` to pytest
through the `PERF_CLI_LAYER` env var (set by the CLI; don't set it yourself). pytest
resolves the settings again from them, so the result JSON records the same values
and sources the CLI used. The CLI exits with pytest's exit code. If the config or a
flag is invalid, it exits with `2`.

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
  will skip because their models are not installed, with the model names. With
  `--no-skip-missing-models` (`benchmark.filters.skip_missing_models: false`) these
  runs are counted in the matrix and listed as **Missing models, will run anyway**
  instead.

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

With a replay (`--config <result JSON or run dir>`, see
[Replaying a run](#replaying-a-run)), `--dry-run` also prints how the setup differs
from the recorded run. Without pytest it can only compare the matrix, not the selected
tests.

If ViPPET cannot be reached, `--dry-run` exits with `2`. A replay whose matrix drifted
exits with `6` unless `--allow-matrix-drift` is given. It exits with `0` in every other
case.

A normal run and direct `pytest --collect-only` print the same matrix after collection
(see [Console output](#console-output)).

#### Report only

`--report-only` rebuilds the HTML report from saved result JSON. It never
contacts ViPPET and never runs jobs.

```bash
python -m perf_helpers.cli --report-only                     # defaults to <results-dir>/latest
python -m perf_helpers.cli --report-only results/latest
python -m perf_helpers.cli --report-only results/bench_A/bench_A.json
python -m perf_helpers.cli --report-only results/bench_A results/bench_B --report-output /tmp/compare.html
```

- Accepted inputs: a result JSON file, a single run directory, or the
  `latest` symlink. The whole results folder is not accepted.
- Several inputs render as one report with several runs; duplicate inputs
  are ignored. Charts and the summary table keep each run's measurements
  separate (an extra "Run" column/legend label appears) even when two runs
  share the same pipeline/variant/stream count, so comparisons across runs
  are not lost. Each run also gets its own system-info card (processor,
  GPU/NPU, memory, OS, discovered devices) labeled by run id, since runs
  being compared may come from different machines.
- Output location:
  - one run: overwrites `<run_dir>/<benchmark_id>.html`;
  - several runs: `<results-dir>/report_YYYYMMDD_HHMMSS.html`;
  - `--report-output PATH` overrides both.
- The JSON must have been saved by the run (`json` listed in
  `results.formats` / `--formats`) and contain the `config` block (see
  [Reports](#reports)). Results written before the `config` block existed are
  rejected; rerun the benchmark.
- The report has a **Configuration** section: each setting with its value and source,
  and per run the config file and its SHA-256, the code revisions, the pytest
  arguments, the replay differences, the selected tests and the included/excluded
  pipeline variants. With several runs, settings that differ between them are listed
  first and highlighted.
- Exit codes: `0` on success; `2` for a missing, unreadable or invalid
  input; `2` for `--report-output` without `--report-only`. If the
  implicit default (`<results-dir>/latest`) is missing, the error
  suggests running a benchmark first or passing an explicit path.

### Direct pytest

You can still call pytest directly. It reads the same YAML and env vars; there are no
CLI flags in this mode:

```bash
# Collect only (preview test matrix)
python -m pytest --collect-only vippet/tests/performance/

# Run a specific pipeline
python -m pytest -m perf -k "object_detection" vippet/tests/performance/

# Generate JUnit XML for CI
python -m pytest -m perf --junitxml=results/perf.xml vippet/tests/performance/
```

### Console output

Every run (CLI or direct pytest) prints these sections in order:

1. **ViPPET readiness**: the `/health` and `/status` checks, then the `/devices`,
   capabilities and version snapshots used for the report.
1. **Discovered hardware**: the ViPPET version and the device names per CPU/GPU/NPU family.
1. **Benchmark matrix**: the same tables as `--dry-run`, covering runs, exclusions
   with reasons, and runs skipped for missing models.
1. **Replay** (replays only): setting, revision and matrix differences from the
   recorded run (see [Replaying a run](#replaying-a-run)).
1. **Per-test status**: one `PASSED`/`FAILED`/`SKIPPED` line per run (`-v` is set in
   `pytest.ini`; pass `-q` after `--` for dots).
1. **Benchmark artefacts**: the run directory, the JSON/CSV/HTML reports, the log file
   and the `latest` link, or why no reports were written. Also a warning if no
   hardware metrics were sampled.
1. pytest's short summary with every skip and failure reason.

The path of the log file is also printed in pytest's header (`benchmark log: ...`), so
it is known even when the run stops at the readiness check.

Logs are not streamed to the console by default. Every run writes its full INFO log to
`bench_<timestamp>.log` in its run directory (see [Reports](#reports)), and the INFO
log of a failed test is also shown in its "Captured log" block. Passing
`--log-cli-level=INFO` to pytest (after `--` for the CLI) streams logs live, which adds
`live log ...` blocks between these sections and splits each per-test status line
around the logs of its job. Per-request `httpx`/`httpcore` lines (e.g. job status polls
and metrics-manager samples) are kept out of the console below WARNING, but they are
written to the log file.

Every error says what happened, why, and how to fix it ("To fix: ..."), naming the
flag, env var or file to change. Errors that stop the run:

| Exit code | Cause                                                                                                  |
|-----------|--------------------------------------------------------------------------------------------------------|
| `1`       | At least one benchmark failed (state, attempts, job id and the fix are shown per test)                 |
| `2`       | Invalid config, or ViPPET unreachable, not the ViPPET API, or not ready within `--readiness-timeout`   |
| `4`       | A filter id in `pipelines`/`variants`/`skip_*` matches nothing and `PERF_ON_UNKNOWN_ID=fail` (default) |
| `6`       | A replay would not benchmark the recorded cases (matrix drift) and `--allow-matrix-drift` is not set   |

The codes follow pytest's numbering. `3` (internal error) and `5` (no tests selected,
e.g. `-k` matches nothing) come from pytest itself, never from the suite.

## Configuration

Settings are combined in this order. Each layer overrides the one before it:

```text
built-in defaults -> YAML config -> environment variables -> CLI flags
```

The YAML file is chosen in this order: `--config`, then `PERF_CONFIG_FILE` (a path),
then `PERF_CONFIG` (a preset name in `config/` or a path), then `default`. Any of them
can also name a result JSON or run directory to replay a run (see
[Replaying a run](#replaying-a-run)). An unknown preset, a missing file, an unknown
YAML key or an invalid value stops the run with an error. Older versions silently fell
back to `default.yaml` instead.

Every YAML key has a CLI flag:

| Flag                         | YAML key                                  | Env var                           |
|------------------------------|-------------------------------------------|-----------------------------------|
| `--config`                   | (selects the YAML file or run to replay)  | `PERF_CONFIG_FILE`, `PERF_CONFIG` |
| `--allow-matrix-drift`       | (replays only; never recorded)            | `PERF_ALLOW_MATRIX_DRIFT`         |
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
| `--capabilities-url`         | `metrics.capabilities_url`                | `VIPPET_CAPABILITIES_URL`         |
| `--metrics-interval`         | `metrics.sample_interval_seconds`         | `PERF_METRICS_INTERVAL`           |
| `--results-dir`              | `results.output_dir`                      | `PERF_RESULTS_DIR`                |
| `--formats`                  | `results.formats`                         |                                   |
| `--[no-]latest-link`         | `results.create_latest_link`              |                                   |
| `--[no-]save-log`            | `results.save_log`                        |                                   |

Notes:

- List flags take comma-separated values, e.g. `--streams 1,3,5` or `--pipelines a,b`.
  `--pipelines '*'` selects all pipelines. Pass `--skip-pipelines ''` to clear a list.
- `--variants` lists the allowed device **families**. A variant runs only if every
  family it uses is allowed: `GPU_NPU` needs both `gpu` and `npu`. So listing
  `gpu_npu` is redundant once `gpu` and `npu` are listed (as in `full.yaml`).
- `--no-skip-missing-models` lets pipelines with missing models run anyway
  (and fail at runtime) instead of being skipped with the missing-model
  reason shown.
- `--metrics-url`/`--capabilities-url` default to `--base-url`'s host (same
  host/port for metrics, same host on port 9090 for capabilities), so setting
  only `--base-url` (or `VIPPET_BASE_URL`) is enough to target a remote
  device; set either flag explicitly to override its default.
- A relative `--results-dir` / `results.output_dir` / `PERF_RESULTS_DIR`
  value is resolved against the current working directory, like any other
  path argument. If you don't set it, it defaults to `results` inside
  `vippet/tests/performance` (an absolute path), so a benchmark run and a
  later `--report-only` agree on where results live regardless of which
  directory the CLI is invoked from — as long as you don't override it
  with a relative path from a different directory.
- The CLI always passes `vippet/tests/performance` to pytest, so arguments after
  `--` can't move collection elsewhere. Paths or node ids after `--` don't narrow
  the run; use `--pipelines`, `--variants`, `--streams` or `-k` instead.

Environment variable defaults:

| Env var                      | Default                                          | Description                                                                                                                                                               |
|------------------------------|--------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `VIPPET_BASE_URL`            | `http://localhost/api/v1`                        | VIPPET API endpoint. Its host (and port) is reused to build the default `VIPPET_METRICS_URL`/`VIPPET_CAPABILITIES_URL` below, so set this alone to target a remote device |
| `VIPPET_METRICS_URL`         | derived from `VIPPET_BASE_URL`'s host/port       | Metrics endpoint (via nginx proxy); set explicitly to override                                                                                                            |
| `VIPPET_CAPABILITIES_URL`    | derived from `VIPPET_BASE_URL`'s host, port 9090 | metrics-manager capabilities endpoint (direct, not nginx-proxied); set explicitly to override                                                                             |
| `VIPPET_JOB_POLL_INTERVAL`   | `2.0`                                            | Job status polling interval (seconds)                                                                                                                                     |
| `VIPPET_JOB_TIMEOUT_SECONDS` | `600`                                            | Max wait for a job, whole seconds                                                                                                                                         |
| `PERF_CONFIG`                | `default`                                        | Config preset (`default`, `quick`, `full`)                                                                                                                                |
| `PERF_CONFIG_FILE`           | (unset)                                          | Explicit YAML path, or a result JSON / run directory to replay; wins over `PERF_CONFIG`                                                                                   |
| `PERF_ALLOW_MATRIX_DRIFT`    | `false`                                          | Replays only: run even if the matrix differs from the recorded one                                                                                                        |
| `PERF_RESULTS_DIR`           | `vippet/tests/performance/results`               | Output directory for reports                                                                                                                                              |
| `PERF_METRICS_INTERVAL`      | `2.0`                                            | HW sampling interval (seconds)                                                                                                                                            |
| `PERF_ON_UNKNOWN_ID`         | `fail`                                           | Unknown id in `pipelines` / `skip_pipelines` / `skip_variants` / `variants`: `fail` aborts the run, `warn` only logs a warning                                            |

This suite reuses some functional-test helper functions (device/pipeline discovery,
job submission/polling) instead of duplicating them; it passes its own resolved
`vippet.base_url` / `vippet.poll_interval` / `vippet.max_job_duration` to them
explicitly. The CLI and direct pytest both resolve settings the same way. 
Numbers must be finite (`nan` and `inf` are rejected). With direct pytest,
an invalid config also prints a one-line error and exits with `2`.

### Replaying a run

Every result JSON records its effective configuration (see [Reports](#reports)). Pass
the JSON or its run directory as the config to run the same benchmark again. All
`--config`/`PERF_CONFIG` paths (like every other path in this suite) are resolved
against the current working directory, so run these from the project root
(`tools/visual-pipeline-and-platform-evaluation-tool`), not from inside
`vippet/tests/performance`:

```bash
# via make (sets PYTHONPATH for you)
make test-performance PERF_CONFIG=vippet/tests/performance/results/bench_20261020_154904
make test-performance PERF_CONFIG=vippet/tests/performance/results/latest PERF_ARGS="--dry-run"

# via the CLI directly — needs the venv active and PYTHONPATH set, as in
# the "CLI" section above:
export PYTHONPATH=vippet/tests/performance
python -m perf_helpers.cli --config vippet/tests/performance/results/bench_20261020_154904
python -m perf_helpers.cli --config vippet/tests/performance/results/latest --dry-run
```

- The recorded values replace the YAML layer, so every setting shows source `yaml`.
  Env vars and CLI flags still override them; each override is listed under
  **Setting changes**. Metrics URLs that were derived from `vippet.base_url` are
  replayed as recorded, so when you change `--base-url`, also pass `--metrics-url`
  and `--capabilities-url` (the replay prints a note).
- Only the recorded tests run; any other test is deselected.
- The replay is compared with the recorded run, printed in the **Replay** section and
  stored in the new result:
  - **Setting changes**: settings that differ, with their new source.
  - **Revision changes**: the suite git commit (suffixed `-dirty` with uncommitted
    changes) or the ViPPET version differs.
  - **Matrix drift**: added or removed cases, missing models or selected tests. The
    replay would measure something else, so it stops with exit code `6`. Pass
    `--allow-matrix-drift` (or `PERF_ALLOW_MATRIX_DRIFT=true`) to run anyway; it
    applies to that run only and is never replayed. It is rejected (exit `2`) when
    the config is not a replay.
  - **Notes**: changed exclusions, pipeline ids or device families that do not
    change what runs.
- A result written by a suite version with different setting keys is refused
  (exit `2`); replay it with that suite version, or copy its settings into a YAML
  config.

## Layout

```text
conftest.py                 # pytest fixtures and parametrize hook
pytest.ini                  # markers and pythonpath
test_pipeline_performance.py  # test module
perf_helpers/
├── cli.py                  # CLI entry point (python -m perf_helpers.cli)
├── config.py               # module constants derived from settings.py
├── discovery.py            # read-only ViPPET queries feeding matrix.py
├── hw_monitor.py           # background HW metric sampler
├── job_outcome.py          # actionable messages for failed/rejected/empty jobs
├── matrix.py               # pure matrix builder, exclusion reasons, matrix rendering, filter-id checks
├── preflight.py            # readiness checks + /devices, /capabilities, /status snapshots, hardware lines
├── reporters.py            # JSON/CSV export, result validation + HTML report generation
├── run_config.py           # result "config" block + replay comparison
├── settings.py             # setting specs + defaults -> YAML -> env -> CLI resolver, replay loading
└── system_info.py          # builds the report's System info block
config/
├── default.yaml            # CPU+GPU+NPU, 1 & 3 streams
├── quick.yaml              # CPU+GPU, 1 stream
└── full.yaml               # all variants, 1/3/5/10 streams
```

## Reports

Each run gets its own directory, `results/bench_YYYYMMDD_HHMMSS/`. The timestamp is the
run's start time and every file in the directory uses it, so the reports and the log of
one benchmark always belong together (the JSON `timestamp` is the same start time). The
exact paths are listed in the run's **Benchmark artefacts** section:

- `.json` — structured results (all test cases + HW metrics) and a `config` block
  with everything needed to reproduce the run: the config selector, file path and
  SHA-256, every resolved setting and its source, the code revisions (suite git
  commit, ViPPET version), the pytest arguments, the resolved matrix, the selected
  tests and, for a replay, its differences from the recorded run
- `.csv` — flat table for spreadsheet analysis
- `.html` — interactive Chart.js report with FPS, utilization, and power charts
- `.log` — the full INFO log of the run, including the per-request HTTP lines hidden from
  the console (`results.save_log`, on by default)

```text
results/
├── bench_20261020_154904/
│   ├── bench_20261020_154904.json
│   ├── bench_20261020_154904.html
│   └── bench_20261020_154904.log
└── latest -> bench_20261020_154904
```

At the end of every run, `latest` is pointed at the run directory, including runs that
failed or stopped at the readiness check, because it is still the latest run. With
`--no-save-log` a run that writes no reports creates no directory and leaves `latest`
unchanged.

Log options (arguments after `--` go to pytest):

```bash
# More detail in the log file
python -m perf_helpers.cli -- --log-file-level=DEBUG
# Write the log somewhere else (no log in the run directory then)
python -m perf_helpers.cli -- --log-file=/tmp/perf.log
# No log file
python -m perf_helpers.cli --no-save-log
```

Rebuild the HTML later with `--report-only` (see [Report only](#report-only)).
