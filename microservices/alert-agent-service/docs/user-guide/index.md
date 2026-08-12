# Alert Agent Service

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/alert-services/alert-agent-service">
     GitHub
  </a>
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/alert-services/alert-agent-service/README.md">
     Readme
  </a>
</div>
hide_directive-->

The Alert Agent Service is a generic, multimodal alert action dispatcher microservice. It receives alert events from upstream detection pipelines (such as video analytics, audio sensors, or IoT devices), reasons over the alert context using an LLM-powered agentic backend, and dispatches one or more configurable action tools — such as logging, webhook notifications, MQTT publishing, and snapshot saving.

## Key Features

- **Multimodal Payloads**: Accept text, image, audio, video, and binary media artifacts attached to alert events.
- **ADK-Powered Dispatch**: LLM-based agentic reasoning via Google ADK and OpenVINO Model Server for intelligent tool selection.
- **Rule-Based Dispatch**: Deterministic tool invocation without LLM overhead when `AGENT_MODE=false`.
- **Subscription Config**: YAML-driven default routing so upstream callers only need to send minimal request fields.
- **Deduplication**: Suppress repeated alerts within configurable time windows to avoid notification floods.
- **Escalation**: Automatically invoke additional tools (e.g., MQTT) after a configurable number of consecutive detections.
- **MCP Integration**: Dynamically extend the tool set with tools from external MCP servers without code changes.
- **SSE / WebSocket Streaming**: Real-time event fanout to monitoring dashboards and downstream consumers.
- **Hot-Reload**: Refresh tool and MCP configurations at runtime without restarting the service.

## Use Cases

This microservice is ideal for:

- Video analytics pipelines requiring automated alert responses (webhook notifications, MQTT publishing, snapshot archiving)
- Edge AI applications that need LLM-guided alert triage
- Multi-sensor environments (cameras, microphones, IoT) with unified alert handling
- Monitoring dashboards consuming real-time alert event streams

## Learn More

- [**Get Started Guide**](./get-started.md)
- [**API Reference**](./api-reference.md)
- [**Release Notes**](./release-notes.md)

<!--hide_directive
:::{toctree}
:hidden:

./get-started.md
./how-it-works.md
./api-reference.md
Release Notes <./release-notes.md>

:::
hide_directive-->
