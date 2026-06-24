# Run On the Host

Use this path when you want to run the Alert Service directly on the host machine using Python.

## Prerequisites

### Python Setup

From the `alert-service/` directory, create a virtual environment and install the required dependencies:

```bash
# Create venv
python -m venv .venv

# Activate venv (Linux/macOS)
source .venv/bin/activate

# On Windows (PowerShell):
# .venv\Scripts\Activate.ps1

# Upgrade pip and install requirements
pip install --upgrade pip
pip install -r requirements.txt
```

### Config Setup

- Create a local `.env` file:
  ```bash
  make init-env
  ```
- Edit `config/config.yaml` to specify alert subscriptions, routing, and deduplication rules.
- If running standalone, you will need a running MQTT broker (like Mosquitto) on port `1883` if your subscriptions include `type: mqtt`. You can run Mosquitto standalone, via docker, or set `MQTT_MODE=external` to use a remote broker.

## Running the Service

### Start

Activate your virtual environment and run the FastAPI app using `uvicorn`:

```bash
source .venv/bin/activate
uvicorn src.main:app --host 127.0.0.1 --port 8000
```

By default, the server binds to:
- host: `127.0.0.1`
- port: `8000`

To customize the bind address or port, modify the uvicorn options or use environment variables.

### Verify

With the service running, hit the health endpoint:

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:
```json
{"status": "healthy"}
```

## API Use Cases and Examples

For API use cases, request examples, and endpoint details, see the [API Reference](../api-reference.md).
