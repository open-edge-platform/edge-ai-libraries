# Release Notes: Alert Service

This page tracks releases of the Alert Service microservice. The most recent release is listed first.

## Version 2026.1.0

First release of the Alert Service as a lightweight, config-driven ingestion, deduplication, and multi-handler routing microservice.

**April 15, 2026**

**New**

- **REST Ingestion API** (`POST /api/v1/alerts`) accepting arbitrary JSON envelopes.
- **Background Worker Loop** driven by FastAPI lifespan hooks and `asyncio.Queue` for non-blocking processing.
- **Configurable Deduplication** using field-hashing (`md5` / `sha1`) over customized fields and sliding TTL windows.
- **Multiple Delivery Handlers** built-in:
  - **Webhook** with independent HTTP POST requests.
  - **MQTT** client publishing to target topics (supports user auth).
  - **WebSocket** real-time alert broadcaster streaming to connected frontend clients.
  - **Log** stdout writer.
- **Independent Target Retries** with customizable attempts and delay intervals.
- **Global Delivery Overrides** using `DELIVERY_HANDLERS` environment variables.
- **New User Guide docs set** including Overview, Get Started, How It Works, Configuration, API Reference, and Troubleshooting documentation.
- Containerization running as non-root user (UID 1000).
- Modular design patterns allowing easy integration of new deduplication strategies or delivery handlers.


