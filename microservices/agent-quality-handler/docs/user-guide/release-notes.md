# Release Notes

## Version 1.0.0

- Standalone Agent Quality Handler with Policy, Analysis, Evidence, and Ticketing graph stages.
- Direct REST API and Prometheus metrics on port `5002`.
- Rule-based fallback mode by default.
- Optional `llm` Compose profile providing OVMS and model download.
- Private Compose MQTT broker plus authenticated support for external MQTT.
- Required external storage API configured by `STORAGE_SERVICE_URL`.
- Event-driven Detection Service batch-complete integration over MQTT.
- Queryable per-agent JSON output history on the named Docker volume.
- Added configurable mounts for downstream-provided agent config and prompt assets.
- Startup validation for runtime configuration and required assets.
- Graph failures reported with status `error`, structured errors, and preserved partial results.

Detection Service, storage, a web UI, and Nginx are not included in this
standalone deployment.
