# Alert Service

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/alert-service">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/alert-service/README.md">
     Readme
  </a>
</div>
hide_directive-->

Alert Service is a lightweight, config-driven microservice designed for ingesting, deduplicating, and routing alerts to multiple delivery targets in real time. Built with FastAPI and asyncio, it handles incoming alert payloads asynchronously, suppresses duplicate events using configurable field-hash strategies inside a sliding window, and dispatches them to destinations like Webhooks, MQTT brokers, local logs, or active WebSocket connections with isolated retries on failure.

## Use Cases

- **Edge Alert Aggregation** — Consolidate alert signals from multiple visual, audio, or physical sensors running at the edge.
- **Duplicate Suppression** — Avoid overloading downstream services (e.g., databases, notification managers) by dropping duplicate alerts within a custom time window.
- **Multi-Destination Fanout** — Route a single ingested alert to different systems simultaneously (e.g., writing to logs for audits, publishing to MQTT for messaging, and triggering webhooks for cloud actions).
- **Real-Time Client Updates** — Stream incoming, processed alerts immediately to frontend UI clients over persistent WebSockets.

## Key Capabilities

- **Flexible REST Ingestion** — Accepts any JSON envelope payload via `POST /api/v1/alerts`.
- **Sliding-Window Deduplication** — In-memory, TTL-based deduplication with flexible field-hash strategies and algorithms (`sha1`, `md5`).
- **Pluggable Delivery Handlers** — Supports Webhook (HTTP POST), MQTT (TCP), WebSocket (native broadcast), and Log (stdout) destinations.
- **Asynchronous Processing** — High-performance background worker utilizing Python's `asyncio` event loop and queue system.
- **Robust Retry Mechanism** — Configurable retry attempts and retry intervals handled independently per delivery target.
- **Config-Driven Architecture** — Subscription matching and routing completely configured via a single `config.yaml` file.

## Next Steps

- [Get Started](./get-started.md) - a step-by-step guide to your first run.
- [Configuration](./get-started/configuration.md) - how to configure subscriptions, deduplication, and handlers.
- [How It Works](./how-it-works.md) - learn about the internal request flow and components.

<!--hide_directive
:::{toctree}
:hidden:

./get-started.md
./how-it-works.md
./api-reference.md
./troubleshooting.md
Release Notes <./release-notes.md>

:::
hide_directive-->
