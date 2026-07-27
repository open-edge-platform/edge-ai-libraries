# Integration Guide

This guide explains how to integrate the Behavioral Analysis Service into an existing application workflow.

The service is MQTT-driven:
- Your upstream application publishes analysis requests.
- The service fetches frames from SeaweedFS, runs pose/pattern analysis (and optional VLM confirmation), then publishes results.

---

## Integration Overview

### Data flow

1. Upstream application stores frames in SeaweedFS.
2. Upstream publishes a request message to the BA request topic.
3. Behavioral Analysis Service consumes the request and fetches frames.
4. Service evaluates configured patterns.
5. Service publishes an outcome message to the BA result topic.
6. Downstream application consumes the result and applies business actions.

---

## Required Changes in Your Application

### 1. Publish requests to MQTT

Your application must publish JSON messages to the configured request topic (default: `ba/requests`).

Required/optional request fields:

| Field | Required | Notes |
|---|---|---|
| `person_id` | Yes | Tracked entity identifier |
| `region_id` | No | Region/zone identifier |
| `entry_timestamp` | No | Used with storage path resolution |
| `scene_id` | No | Scene identifier |
| `last_frame_ts` | No | Optional cap for frame fetch range |

Example payload:

```json
{
  "person_id": "person-042",
  "region_id": "shelf-B",
  "entry_timestamp": "1700001000000",
  "scene_id": "store-01",
  "last_frame_ts": "1700001030000"
}
```

### 2. Align SeaweedFS frame path contract

Frames must be readable by the service under:

```text
{SEAWEEDFS_BUCKET}/{entity_id}/{region_id}/{entry_timestamp}/frames/{timestamp}.jpg
```

Notes:
- Bucket name is configurable via `SEAWEEDFS_BUCKET`.
- Filenames should preserve timestamp ordering because the service sorts by timestamp name.

### 3. Consume result messages

Your application (or another downstream consumer) must subscribe to the configured result topic (default: `ba/results`).

Typical result fields:

| Field | Notes |
|---|---|
| `person_id`, `region_id`, `entry_timestamp`, `scene_id`, `last_frame_ts` | Echo/context fields |
| `status` | `"no_enough_data"`, `"no_match"`, `"suspicious"` |
| `confidence` | Detection confidence |
| `frames_analyzed` | Number of frames processed |
| `vlm_response` | Parsed VLM payload or `null` |
| `pattern_id` | Present when pattern matched |
| `description` | Pattern description when available |
| `vlm_confirmed` | Optional boolean when VLM path is active |

---

## Configuration Mapping Checklist

Ensure your application-side assumptions match service configuration:

- MQTT broker and topics:
  - `MQTT_HOST`, `MQTT_PORT`
  - `BA_REQUEST_TOPIC`, `BA_RESULT_TOPIC`
- SeaweedFS endpoint and bucket:
  - `SEAWEEDFS_ENDPOINT`, `SEAWEEDFS_BUCKET`
- Frame thresholds and fetch behavior:
  - `MIN_FRAMES_FOR_DETECTION`, `MAX_FRAMES_TO_FETCH`, `POSE_FRAMES_COUNT`
- Model path/device:
  - `YOLO_POSE_MODEL`, `GST_INFERENCE_DEVICE`
- Pattern configuration file:
  - `PATTERN_CONFIG_PATH`
- Optional VLM path:
  - `VLM_ENABLED`, `VLM_ENDPOINT`, `VLM_MODEL_NAME`

Use [Configuration](./get-started/configuration.md) as the source of truth for variable definitions and defaults.

---

## End-to-End Validation

Use this sequence after integration:

1. Confirm connectivity:
- Service can reach MQTT broker.
- Service can reach SeaweedFS.
- If enabled, service can reach OVMS VLM endpoint.

2. Confirm frame availability:
- Verify frames exist in the expected SeaweedFS path for a known `person_id`/`region_id`/`entry_timestamp`.

3. Publish one known request:
- Send a request on the configured BA request topic with matching identifiers.

4. Verify service processing logs:
- Confirm request received, frames fetched, pose analysis executed.

5. Verify result publication:
- Confirm one output event on BA result topic with expected status and metadata.

---

## Common Integration Pitfalls

### Topic mismatch

Symptoms:
- Requests are published but never consumed.
- No BA results observed.

Checks:
- Verify publisher topic equals `BA_REQUEST_TOPIC`.
- Verify consumer topic equals `BA_RESULT_TOPIC`.

### Frame path mismatch

Symptoms:
- Frequent `no_enough_data` status.

Checks:
- Validate bucket and object key structure match service expectations.
- Validate identifiers in request match identifiers used in stored frame path.

### Cross-container network isolation

Symptoms:
- Service starts but cannot reach SeaweedFS/MQTT/OVMS.

Checks:
- Ensure services share a reachable Docker network.
- Ensure endpoint hostnames resolve from the behavioral-analysis container.

### Configuration drift between environments

Symptoms:
- Works in one environment, fails in another.

Checks:
- Compare `.env`/`.env.local` and runtime variables per environment.
- Reconfirm topic names, bucket name, and model path.

---

## Related Documentation

- [Get Started](./get-started.md)
- [How It Works](./how-it-works.md)
- [API Reference](./api-reference.md)
- [Configuration](./get-started/configuration.md)
- [Troubleshooting](./troubleshooting.md)
