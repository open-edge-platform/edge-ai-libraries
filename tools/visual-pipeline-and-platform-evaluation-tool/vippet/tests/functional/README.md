# VIPPET Functional Tests

Functional tests that exercise the VIPPET API end-to-end.

## Requirements

- Python 3.12+
- VIPPET API running and reachable (default: `http://localhost/api/v1`)

## Prerequisites

Before running the tests, ensure the required models are installed.

### Smoke tests

Smoke tests require the default models to be installed. Run the following command to install them:

```bash
make install-models-force
```

All default models will be pre-selected. Simply click **OK** to proceed with the installation.

### Full tests

Full tests require **all** available models to be installed. Run:

```bash
make install-models-all
```

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

| Environment variable          | Default                   | Description                      |
|-------------------------------|---------------------------|----------------------------------|
| `VIPPET_BASE_URL`             | `http://localhost/api/v1` | Base URL of the VIPPET API       |
| `VIPPET_JOB_TIMEOUT_SECONDS`  | `600`                     | Max wait time for job completion |
| `VIPPET_JOB_POLL_INTERVAL`    | `2.0`                     | Polling interval in seconds      |
