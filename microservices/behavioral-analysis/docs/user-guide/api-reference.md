# API Reference

The Behavioral Analysis Service processes requests through MQTT messaging. There is no tested REST API exposed in the current release.

---

## MQTT Interface

### ba/requests (Subscribe)

The service subscribes to this topic on startup.

**Payload schema (JSON):**

| Field | Type | Required | Description |
|---|---|---|---|
| `person_id` | `string` | Yes | Tracked person identifier |
| `region_id` | `string` | No | Zone or region identifier |
| `entry_timestamp` | `string` | No | Timestamp when the person entered the region |
| `scene_id` | `string` | No | Scene identifier |
| `last_frame_ts` | `string` | No | Timestamp of the most recent stored frame (for capping fetch range) |

**Example payload:**
```json
{
  "person_id": "person-042",
  "region_id": "shelf-B",
  "entry_timestamp": "1700001000000",
  "scene_id": "store-01",
  "last_frame_ts": "1700001030000"
}
```

### ba/results (Publish)

The service publishes one result message per processed request.

**Payload schema (JSON):**

| Field | Type | Description |
|---|---|---|
| `person_id` | `string` | Person identifier from the request |
| `region_id` | `string` | Region from the request |
| `entry_timestamp` | `string` | Entry timestamp from the request |
| `scene_id` | `string` | Scene from the request |
| `last_frame_ts` | `string` | Frame timestamp from the request |
| `status` | `string` | `"no_enough_data"`, `"no_match"`, `"suspicious"` |
| `confidence` | `float` | Detection confidence (0.0–1.0) |
| `vlm_response` | `object` \| `null` | Parsed VLM JSON response or `null` |
| `frames_analyzed` | `integer` | Number of frames processed |
