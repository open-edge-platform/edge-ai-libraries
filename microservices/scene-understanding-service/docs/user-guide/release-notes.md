# Release Notes: Scene Understanding Service

This page tracks releases of the Scene Understanding Service microservice. The
most recent release is listed first; older entries are preserved for history.

## Version 2026.2.0

**Release Date:** September 9, 2026

Scene Understanding Service is a generic microservice for multi-scene, zone-based
behavioral analysis. Its behavior is defined entirely through two YAML files
(`scene-config.yaml` and `rules.yaml`), enabling scenarios such as retail loss
prevention, restricted-area monitoring, and other zone-based use cases without
code changes.

**New:**

- Multi-scene, multi-camera person tracking with per-person session state
  (zone visits, dwell time, behavioral flags).
- Declarative rule engine: thresholds and detection rules are changed through
  configuration, with support for severity escalation and per-session
  de-duplication of alerts.
- Optional deeper analysis: escalate selected events to a behavioral-analysis
  worker (pose + visual language model) for concealment-style detection.
- Automatic zone discovery from Scenescape at startup, with the ability to add
  or update zones at runtime.
- Optional evidence-frame capture and routing of alerts to a downstream alert
  service.
- Ships self-contained with sample configuration for standalone evaluation and
  drop-in use with any Scenescape-based deployment.

**Known Issues:**

- The service requires a reachable Scenescape deployment (including the
  analytics component on Scenescape 2026.2.0) to produce zone-based events
  and alerts.
- Alert visibility depends on a reachable alert service.

## Version 0.1.0

First release of the Scene Understanding Service as a self-contained,
reusable microservice for multi-scene behavioral analysis and suspicious
activity detection, built for edge deployment on Intel hardware.

**Release Date:** June 18, 2026

**New:**

- Scenescape MQTT-driven, multi-scene, multi-camera person tracking with a
  per-person session state machine (zone visits, dwell time, flags).
- Declarative YAML rule engine (`rules.yaml`) producing `alert` and
  `escalate` actions; thresholds and rules change without code edits.
- Optional behavioral-analysis escalation (pose + VLM) integrated over the
  `ba/requests` / `ba/results` MQTT topics.
- Zone auto-discovery from the Scenescape REST API at startup, with on-demand
  re-discovery via `POST /api/v1/sus/zones/discover`.
- Optional SeaweedFS evidence-frame capture and alert-service routing.
- REST API under `/api/v1/sus` for session, zone, and alert state, plus
  `/health`.
- Self-contained image with bundled sample config (`scene-config.yaml`,
  `rules.yaml`) that runs standalone; consuming applications override via a
  read-only volume mount.
- New User Guide doc set: overview, get-started, how-it-works, configuration,
  api-reference, and troubleshooting, plus an architecture diagram.

**Known issues:**

- The service is an event consumer/producer; it requires a reachable
  Scenescape deployment (MQTT + REST) to produce meaningful output.
- The alert endpoints depend on a reachable alert-service; they return empty
  results when alerting is disabled or the alert-service is unavailable.
