# Agent Quality Handler

The Agent Quality Handler is a standalone, configuration-driven service that runs an Agentic Predictive Maintenance graph against detections from a required external storage API.

## Capabilities

- Policy, Analysis, Evidence, and Ticketing agents
- Rule-based fallback mode or profile-gated LLM mode
- MQTT detection ingestion, including authenticated connections to external brokers
- Custom use-case config and prompt mounts
- Direct REST API and Prometheus metrics on port `5002`
- Explicit graph errors with preserved partial results

Detection Service and storage are external. The default Compose deployment
includes the agent and a private MQTT broker; the `llm` profile adds OVMS and
model download. It does not include a UI or Nginx.

## Documentation

- [Get Started](./get-started.md)
- [System Requirements](./get-started/system-requirements.md)
- [How It Works](./how-it-works.md)
- [Build from Source](./build-from-source.md)
- [API Reference](./api-reference.md)
- [Agent Service Integration Guide](./agent-service-integration-guide.md)
- [Troubleshooting](./troubleshooting.md)
- [Release Notes](./release-notes.md)

<!--hide_directive
:::{toctree}
:hidden:

get-started
how-it-works
Build From Source <build-from-source.md>
How to Integrate service <agent-service-integration-guide.md>
api-reference
troubleshooting
release-notes
:::
hide_directive-->
