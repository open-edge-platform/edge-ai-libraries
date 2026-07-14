# Run Standalone

Running the service outside Docker requires Python 3.12, OpenVINO Runtime, and all Python dependencies installed locally. This mode is primarily useful for development and testing.

> **Note:** The container image (`intel/dlstreamer:2026.1.0-ubuntu24`) provides OpenVINO and GStreamer pre-installed. Replicating this environment locally requires manual OpenVINO installation.

---

## Prerequisites

- Python 3.12
- OpenVINO Runtime (matching the version in `intel/dlstreamer:2026.1.0-ubuntu24`)
- Git (required for the `git+https://` dependency in `requirements.txt`)
- Running instances of SeaweedFS, MQTT broker, and OVMS (if VLM is enabled)
- YOLO-Pose model files (`.xml` + `.bin`) accessible at a local path

---

## 1. Install Dependencies

```bash
# From the behavioral-analysis/ directory
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

---

## 2. Configure the Environment

Use a local environment file and source it in your shell:

```bash
cp .env .env.local
# Edit .env.local with your deployment-specific values
set -a
source .env.local
set +a
```

See [Configuration](configuration.md) for the full list of required variables.

---

## 3. Start the Service

```bash
# From the behavioral-analysis/ directory
source .venv/bin/activate
PYTHONPATH=src python3 -m uvicorn main:app --host 0.0.0.0 --port 8080
```

The service starts on port `8080` by default. To use a different port:

```bash
PYTHONPATH=src python3 -m uvicorn main:app --host 0.0.0.0 --port 8085
```

To enable auto-reload during development:

```bash
PYTHONPATH=src python3 -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

---

## 4. Verify the Service

```bash
curl http://localhost:8080/health
```

Expected response:
```json
{
  "status": "healthy",
  "model_loaded": true,
  "seaweedfs_connected": true
}
```

---

## 5. Submit a Test Request

```bash
curl -X POST http://localhost:8080/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "test-person-001",
    "pattern_id": "shelf_to_waist"
  }'
```

---

## Runtime Arguments

Uvicorn arguments relevant to this service:

| Argument | Description | Example |
|---|---|---|
| `--host` | Bind address | `0.0.0.0` |
| `--port` | Listen port | `8080` |
| `--reload` | Auto-reload on code changes (dev only) | — |
| `--workers` | Number of worker processes (not recommended — service has singleton YOLO model) | `1` |
| `--log-level` | Uvicorn log level | `info`, `debug` |

---

## Logs

Logs are written to standard output. Redirect to a file:

```bash
PYTHONPATH=src python3 -m uvicorn main:app --host 0.0.0.0 --port 8080 > app.log 2>&1 &
```

---

## Shutdown

Send `SIGTERM` or press `Ctrl+C`. The service performs a graceful shutdown:
1. MQTT consumer awaits all in-flight analyses.
2. VLM HTTP client connection pool is closed.

```bash
# If running in background
kill -TERM <uvicorn-pid>
```

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'openvino'`

Install OpenVINO Runtime for Python:
```bash
pip install openvino
```

### `ModuleNotFoundError: No module named 'gstgva'`

`gstgva` is provided by the DL Streamer base image and is not available in standalone Python environments. The service's `YOLOPoseOV` wrapper does not require it; this error only appears if an import path includes the GStreamer extension.

### SeaweedFS or MQTT connection errors at startup

Ensure the external services are running and the environment variables point to the correct host/port. See [Troubleshooting](../troubleshooting.md) for details.
