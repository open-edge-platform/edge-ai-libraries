# VIPPET Functional Tests

Functional tests that exercise the VIPPET API end-to-end.

## Requirements

- Python 3.12+
- VIPPET API running and reachable (default: `http://localhost/api/v1`)

## Prerequisites

Before running the tests, ensure the required models are installed via the **Models** page
in the web UI (or via the `/api/v1/models` API endpoints). The backend proxies install
requests to the `model-download` microservice.

### Smoke tests

Smoke tests require the default-recommended models (those returned with
`default: true` by the `/api/v1/models` API, i.e. models referenced by at
least one predefined pipeline) to be installed.

### Full tests

Full tests require **all** models defined under `vippet/models/*.yaml`
(one YAML file per model) to be installed.

### Input videos

ViPPET downloads its sample videos on demand (UI **Videos** page), so a fresh ViPPET may
have none. Tests that run a pipeline skip each pipeline variant whose input video is
missing, with the reason: download the sample video on the **Videos** page, upload a
video that is not a sample, or select an input video in the pipeline's Input node. The
functional tests never download videos themselves. The performance CLI can download
them, see `--download-missing-videos` in
[the performance suite README](../performance/README.md#downloading-missing-videos).

## Test behavior

### Device-based pipeline variants

The test suite automatically queries the `/devices` endpoint at runtime to discover available hardware.
Based on the detected devices, tests will run the appropriate pipeline variants (e.g., CPU, GPU, NPU)
without any manual configuration.

### USB camera tests

Tests that use a USB camera as a pipeline source are only executed when a camera is detected.
The test suite queries the `/cameras` endpoint at startup — if no camera is found, those tests are automatically skipped.

## Running

```bash
python3 -m pytest vippet/tests/functional/
```

Run a specific test file:

```bash
python3 -m pytest vippet/tests/functional/test_density_job_flow.py
```

Or via Makefile:

```bash
# Run smoke tests only
make test-smoke

# Run full functional tests
make test-full
```

## Configuration

| Environment variable                     | Default                   | Description                                               |
|------------------------------------------|---------------------------|-----------------------------------------------------------|
| `VIPPET_BASE_URL`                        | `http://localhost/api/v1` | Base URL of the VIPPET API; set to target a remote device |
| `VIPPET_JOB_TIMEOUT_SECONDS`             | `600`                     | Max wait time for job completion                          |
| `VIPPET_JOB_POLL_INTERVAL`               | `2.0`                     | Polling interval in seconds                               |
| `VIPPET_BENCHMARK_SUITE_TIMEOUT_SECONDS` | `1800`                    | Max wait time for a full benchmark suite run to complete  |
