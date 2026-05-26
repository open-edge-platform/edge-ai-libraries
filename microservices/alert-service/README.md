# Alert Service

A lightweight, config-driven microservice for ingesting, deduplicating, and routing alerts to multiple delivery targets in real time. Built with **FastAPI** and **asyncio**, the Alert Service accepts any JSON alert payload via a REST API, applies configurable field-hash deduplication to suppress duplicates within a sliding time window, and fans out each alert to one or more pluggable delivery handlers — **Webhook**, **MQTT**, and **Log** — with automatic retry on failure. All subscription rules, dedup parameters, and delivery routing are defined in a single YAML configuration file, making it easy to adapt the service to different alert types and downstream systems without changing code.

---

## Documentation

| Document | Description |
|---|---|
| [Overview & Architecture](docs/overview-and-architecture.md) | Features, high-level design, component tables, delivery handlers, worker/retry, MQTT mode, project structure |
| [Getting Started](docs/get-started.md) | Prerequisites, clone & setup, Makefile reference, running tests & coverage |
| [Configuration & Customization](docs/configure.md) | Environment variables, MQTT mode, delivery handlers override, deduplication guide, MQTT guide, WebSocket testing, QA checklist |

---

## Quick Start

```bash
make init-env        # create .env from .env.example
make build           # build Docker image
make up              # start services
curl http://localhost:8000/api/v1/health   # verify
```

Post an alert:

```bash
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"test","metadata":{"zone":"A"},"payload":{"msg":"hello"}}'
```

See [Getting Started](docs/get-started.md) for full details.
