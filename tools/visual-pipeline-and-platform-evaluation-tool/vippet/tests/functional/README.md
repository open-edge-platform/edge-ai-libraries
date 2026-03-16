# VIPPET Functional Tests

Functional tests that exercise the VIPPET API end-to-end.

## Requirements

- Python 3.12+
- VIPPET API running and reachable (default: `http://localhost/api/v1`)

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
