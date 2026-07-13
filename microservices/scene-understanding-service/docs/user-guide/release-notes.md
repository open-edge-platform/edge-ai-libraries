# Release Notes: Scene Understanding Service

This page tracks releases of the Scene Understanding Service microservice. The
most recent release is listed first; older entries are preserved for history.

## Version 0.1.0

First release of the Scene Understanding Service as a self-contained,
reusable microservice for multi-scene behavioral analysis and suspicious
activity detection, built for edge deployment on Intel hardware.

**June 18, 2026**

**New**

- SceneScape MQTT-driven, multi-scene, multi-camera person tracking with a
  per-person session state machine (zone visits, dwell time, flags).
- Declarative YAML rule engine (`rules.yaml`) producing `alert` and
  `escalate` actions; thresholds and rules change without code edits.
- Optional behavioral-analysis escalation (pose + VLM) integrated over the
  `ba/requests` / `ba/results` MQTT topics.
- Zone auto-discovery from the SceneScape REST API at startup, with on-demand
  re-discovery via `POST /api/v1/lp/zones/discover`.
- Optional SeaweedFS evidence-frame capture and alert-service routing.
- REST API under `/api/v1/lp` for session, zone, and alert state, plus
  `/health`.
- Self-contained image with bundled sample config (`scene-config.yaml`,
  `rules.yaml`) that runs standalone; consuming applications override via a
  read-only volume mount.
- New User Guide doc set: overview, get-started, how-it-works, configuration,
  api-reference, and troubleshooting, plus an architecture diagram.

**Known issues**

- The service is an event consumer/producer; it requires a reachable
  SceneScape deployment (MQTT + REST) to produce meaningful output.
- The alert endpoints depend on a reachable alert-service; they return empty
  results when alerting is disabled or the alert-service is unavailable.
