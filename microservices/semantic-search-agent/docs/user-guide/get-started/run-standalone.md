# Run On the Host

Use this path when you want to run the Semantic Search Agent directly on the host machine using Python.

## Prerequisites

### Python Setup

From the `semantic-search-agent/` directory, create a virtual environment and install the required dependencies:

```bash
# Create venv
python -m venv venv

# Activate venv (Linux/macOS)
source venv/bin/activate

# On Windows (PowerShell):
# venv\Scripts\Activate.ps1

# Upgrade pip and install requirements
pip install --upgrade pip
pip install -r requirements.txt
```

### Config Setup

- Create a local `.env` file:
  ```bash
  cp .env.example .env
  ```
- Edit `.env` to set `DEFAULT_MATCHING_STRATEGY` and the corresponding VLM backend variables.
- Review `config/inventory.json` and `config/orders.json` and update them as needed. The service reads these at startup and caches them in memory.
- If running standalone with `CACHE_BACKEND=redis`, you will need a running Redis instance on the configured host and port (default: `localhost:6379`).

## Running the Service

### Start

Activate your virtual environment and run the FastAPI app using `uvicorn`:

```bash
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8080
```

By default, the server binds to:
- host: `127.0.0.1`
- port: `8080`

To enable auto-reload for development:

```bash
uvicorn app.main:app --reload --port 8080
```

Or use the Makefile shortcut:

```bash
make run
```

### Verify

With the service running, hit the health endpoint:

```bash
curl http://localhost:8080/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "semantic-search-agent",
  "version": "2026.1.0",
  "vlm_backend": "ovms",
  "vlm_status": "connected",
  "uptime_seconds": 3.42
}
```

## API Documentation

The service exposes interactive Swagger UI documentation while running:

```
http://localhost:8080/docs
```

## API Use Cases and Examples

For API use cases, request examples, and endpoint details, see the [API Reference](../api-reference.md).
