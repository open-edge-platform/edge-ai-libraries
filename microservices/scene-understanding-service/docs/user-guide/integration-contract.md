# Integration Contract

This page defines the **external interface** of the Scene Understanding Service
so that any application can integrate with it — or supply a compatible
behavioral-analysis worker — without reading the source. Everything here is a
stable contract: topic strings, payload schemas, QoS, and the values the rule
engine understands.

The service has three integration surfaces:

1. **Inbound MQTT** — SceneScape events it consumes (its data source).
2. **BA MQTT** — the request/result exchange with a behavioral-analysis worker.
3. **REST API** — read/query endpoints (see [API Reference](./api-reference.md)).

All MQTT traffic uses **QoS 1** and messages are **not retained**. Because
nothing is retained, a subscriber must be connected when a message is published
or that message is missed — start the consumer before the producer, or rely on
the event-driven re-publish cadence rather than replay.

---

## 1. Prerequisite: SceneScape

The service is **not** a standalone event source. It requires a reachable
[SceneScape](https://github.com/open-edge-platform/scenescape) deployment that
provides:

| Dependency          | Purpose                                                        |
| ------------------- | -------------------------------------------------------------- |
| SceneScape MQTT broker | Source of all person/zone/scene events (see topics below).  |
| SceneScape REST API | Zone auto-discovery at startup (region UUID → name mapping).   |

A use case that has no SceneScape deployment cannot use this service as-is; it
would need an adapter that republishes its events onto the SceneScape topic
shapes described below.

---

## 2. Inbound MQTT (SceneScape → service)

The service **subscribes** to the following topics on connect. The topic
patterns are configurable in `scene-config.yaml` under `mqtt` (defaults shown).

| Topic pattern (default)              | Config key                    | Meaning                                                   |
| ------------------------------------ | ----------------------------- | --------------------------------------------------------- |
| `scenescape/data/scene/+/+`          | `scene_data_topic_pattern`    | Scene object data: `.../{scene_id}/{object_type}`.        |
| `scenescape/data/region/+/+/+`       | _(fixed)_                     | Continuous per-region object feed.                        |
| `scenescape/event/region/+/+/+`      | `region_event_topic_pattern`  | Region enter/exit events: `.../{scene_id}/{region_id}/…`. |
| `scenescape/image/camera/+`          | `image_topic_pattern`         | Camera image frames: `.../{camera_name}`.                 |

The service **publishes** camera image requests back to SceneScape:

| Topic pattern (default)                     | Config key         | Meaning                                    |
| ------------------------------------------- | ------------------ | ------------------------------------------ |
| `scenescape/cmd/camera/{camera_name}`       | `cmd_topic_pattern` | `getimage` command to pull a live frame.   |

> Payloads on these topics follow the SceneScape schema and are owned by
> SceneScape, not by this service.

---

## 3. Behavioral-Analysis (BA) MQTT contract

This is the interface any behavioral-analysis worker must implement. The two
topic names are configurable and **must be identical on both sides** (see
[Configuration](./get-started/configuration.md)):

| Direction                | Topic (default) | Config key / env                                   |
| ------------------------ | --------------- | -------------------------------------------------- |
| service → BA worker      | `ba/requests`   | `mqtt.ba_request_topic` / `BA_REQUEST_TOPIC`       |
| BA worker → service      | `ba/results`    | `mqtt.ba_result_topic` / `BA_RESULT_TOPIC`         |

### 3.1 Request: `ba/requests`

Published by the service once per capture cycle for a person in a monitored
zone (frames already stored in the shared `behavioral-frames` bucket).

```json
{
  "person_id": "string",        // tracked person / entity id (required)
  "region_id": "string",        // region UUID the person is in
  "entry_timestamp": "string",  // ISO-8601 time the person entered the zone
  "scene_id": "string",         // scene UUID
  "last_frame_ts": "string"     // timestamp of the most recent stored frame
}
```

A worker that receives a message with an empty `person_id` must ignore it.

### 3.2 Result: `ba/results`

Published by the BA worker exactly once per request. The service folds it back
into the person session; the rule engine matches on `status` and `confidence`.

```json
{
  "person_id": "string",
  "region_id": "string",
  "entry_timestamp": "string",
  "scene_id": "string",
  "last_frame_ts": "string",
  "status": "suspicious | no_match | no_enough_data",
  "confidence": 0.0,            // float 0.0–1.0
  "vlm_response": "string|null",// optional human-readable reasoning
  "frames_analyzed": 0          // number of frames the worker inspected
}
```

The echoed `person_id` / `region_id` / `entry_timestamp` / `scene_id` /
`last_frame_ts` fields must match the originating request so the service can
correlate the verdict to the correct visit.

### 3.3 `status` values (enum)

| Value            | Meaning                                                         |
| ---------------- | -------------------------------------------------------------- |
| `suspicious`     | Behavior confirmed (e.g. pose pattern + VLM). Triggers alerts. |
| `no_match`       | Analysis ran but did not confirm suspicious behavior.          |
| `no_enough_data` | Not enough frames/data to analyze; treated as inconclusive.    |

`rules.yaml` matches on these values (e.g. `match_value: suspicious`). A custom
worker may only emit values from this enum, or extend `rules.yaml` to recognize
new ones.

---

## 4. Versioning & compatibility

- Treat the topic strings and the JSON field names above as the **public API**.
- Prefer **additive** changes (new optional fields). Removing or renaming a
  field, or changing a `status` value, is a breaking change for every consumer.
- Both sides must share the same MQTT broker (`MQTT_HOST` / `MQTT_PORT`) and the
  same topic values. Define these once (e.g. a shared `.env`) and inject them
  into every service so they cannot drift.

---

## 5. REST API

Read/query endpoints (sessions, zones, status) are documented separately in the
[API Reference](./api-reference.md). The REST surface is for observability and
control; the event-driven behavior above is the primary integration path.
