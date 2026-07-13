# API Reference

Base URL: `http://127.0.0.1:8082` (default). All loss-prevention endpoints are
served under the `/api/v1/lp` prefix and return JSON.

## `GET /health`

Liveness probe.

Response:

```json
{"status": "healthy"}
```

## `GET /api/v1/lp/status`

Service readiness and runtime statistics (active sessions, resolved zones,
connection state).

```bash
curl --noproxy '*' http://127.0.0.1:8082/api/v1/lp/status
```

## Sessions

### `GET /api/v1/lp/sessions`

Return active person sessions with a per-zone visit summary. By default, only
sessions whose SceneScape re-id state has progressed beyond initial collection
are returned. Pass `?include_pending=true` to include transient tracks.

| Query             | Default | Description                              |
| ----------------- | ------- | ---------------------------------------- |
| `include_pending` | `false` | Include `pending_collection` tracks.     |

### `GET /api/v1/lp/sessions/count`

Count of active sessions.

### `GET /api/v1/lp/sessions/{object_id}`

Detail for a single person session.

| Query      | Default | Description                       |
| ---------- | ------- | --------------------------------- |
| `scene_id` | _(any)_ | Restrict to a specific scene UUID.|

## Zones

### `GET /api/v1/lp/zones`

All resolved zones (region UUID → type mapping).

### `GET /api/v1/lp/zones/names`

Zone name → type mapping as defined in `scene-config.yaml`.

### `PUT /api/v1/lp/zones/{region_id}`

Manually register or update a zone mapping at runtime.

### `DELETE /api/v1/lp/zones/{region_id}`

Remove a zone mapping.

### `POST /api/v1/lp/zones/discover`

Trigger zone re-discovery from the SceneScape REST API.

## Alerts

### `GET /api/v1/lp/alerts`

Recent alerts, proxied from the alert-service.

| Query        | Default | Description                          |
| ------------ | ------- | ------------------------------------ |
| `alert_type` | _(all)_ | Filter by alert type.                |
| `object_id`  | _(all)_ | Filter by person `object_id`.        |
| `limit`      | `50`    | Max results (1–500).                 |

### `GET /api/v1/lp/alerts/count`

Total alert count.

> The alert endpoints require a reachable alert-service. When alerting is
> disabled or the alert-service is unavailable, these return empty results.

## Supporting Resources

- Startup and deployment guides:
  - [Get Started](./get-started.md)
  - [Run with Docker](./get-started/run-container.md)
  - [Run on Host](./get-started/run-standalone.md)
- Configuration of scenes, zones, and rules:
  - [Configuration Guide](./get-started/configuration.md)
