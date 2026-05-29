# Getting Started

## Prerequisites

| Tool | Version |
|---|---|
| Docker | 24+ |
| Docker Compose | v2 plugin (`docker compose`) |

---

## 1. Clone & Navigate

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries/microservices/alert-service
```

---

## 2. Set Up Environment

```bash
make init-env        # copies .env.example → .env (prompts before overwrite)
```

Edit `.env` to taste — see [Configuration](configure.md) for details.

---

## 3. Build & Run

```bash
make build           # build Docker image
make up              # start services (includes Mosquitto if MQTT_MODE=embedded)
make logs            # tail container logs
make down            # stop & remove containers
```

Instead of building locally, you can directly use the official Docker image:
docker pull intel/alert-service:0.0.1


---

## 4. Verify

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Post an alert
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"CONCEALMENT","metadata":{"poi_id":"person-001","camera_id":"cam-north-01"},"timestamp":"2025-01-15T10:30:00Z"}'
```

---

## Makefile Reference

| Target | Description |
|---|---|
| `make build` | Build the Docker image |
| `make up` | Start services (detached). Starts Mosquitto if `MQTT_MODE=embedded` |
| `make down` | Stop and remove containers |
| `make logs` | Tail container logs |
| `make test` | Install dev dependencies and run `pytest` locally |
| `make coverage` | Run tests with coverage summary (terminal) |
| `make coverage-html` | Generate HTML coverage report in `htmlcov/` |
| `make init-env` | Copy `.env.example` → `.env` (prompts if `.env` exists) |
| `make clean` | Remove containers, images, volumes, and `htmlcov/` |

---

## Running Tests

### Inside Docker (recommended)

```bash
make test              # quick pass/fail
make coverage          # terminal coverage report
make coverage-html     # HTML report → htmlcov/index.html
```

### Locally with Poetry

```bash
poetry install
poetry run pytest
poetry run pytest --cov=src --cov-report=term-missing
```

### Locally with venv

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
```

---

## Sample API Requests

### POST an alert (full payload)

```bash
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "alert_type": "INTRUSION",
    "metadata": {
      "camera_id": "cam-01",
      "zone": "entrance"
    },
    "payload": {
      "confidence": 0.95,
      "bbox": [100, 200, 300, 400]
    }
  }'
```

### POST an alert (minimal)

```bash
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"LOITERING","metadata":{"zone_id":"zone-5"}}'
```

> **Note:** `alert_type` matching is **case-sensitive**. The value must exactly match the subscription name in `config/config.yaml` (e.g. `INTRUSION`, not `intrusion`).

### Health check

```bash
curl http://localhost:8000/api/v1/health
```

---

**Next:** [Overview & Architecture](overview-and-architecture.md) · [Configuration & Customization](configure.md)
