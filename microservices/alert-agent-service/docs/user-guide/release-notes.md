# Release Notes: Alert Agent Service

## Version 0.1.0

**TBD**

**New**

- Initial release of the Alert Agent Service.
- Generic multimodal alert action dispatcher supporting text, image, audio, video, and binary payloads.
- ADK-powered dispatch mode using Google Agent Development Kit (ADK) backed by OpenVINO Model Server (OVMS) with the `Phi-4-mini-instruct-int4-ov` model.
- Rule-based dispatch mode (`AGENT_MODE=false`) for deterministic tool invocation without LLM overhead.
- Four built-in action tools: `log_alert`, `trigger_webhook`, `capture_snapshot`, `publish_mqtt`.
- YAML-based subscription configuration for per-alert-name default tool routing, deduplication rules, and escalation policies.
- Deduplication engine with `field_hash` strategy to suppress repeated alerts within configurable time windows.
- Escalation support — additional tools triggered after a configurable consecutive-detection threshold.
- MCP (Model Context Protocol) client integration to extend the tool set from external HTTP-based MCP servers.
- Server-Sent Events (SSE) stream (`GET /api/v1/events`) and WebSocket stream (`GET /api/v1/ws`) for real-time alert event fanout.
- Hot-reload endpoints for tools (`POST /api/v1/tools/reload`) and MCP servers (`POST /api/v1/mcp/reload`) without service restart.
- Subscription management endpoint (`GET /api/v1/subscriptions`) to inspect loaded routing rules.
- Liveness probe (`GET /api/v1/health`).
- Docker Compose deployment with OVMS LLM sidecar container.
- Helm chart support for Kubernetes deployment.

**Known Issues**

- OVMS LLM container startup may take up to 5 minutes while the model is downloaded and loaded for the first time.
- MCP integration supports HTTP transport only; stdio/process-based MCP transports are not currently supported.
- The `capture_snapshot` tool only writes disk snapshots when the image payload uses `encoding=base64`. URI-referenced images are logged but not downloaded or saved.
- Intel does not support Edge Manageability Framework deployment currently.
