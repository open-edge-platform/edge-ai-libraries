<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Intersection Map View

## Overview

The Intersection Map View pins video search results on the traffic
intersection they were recorded at. Select **Map View** in the search results
header: a map slides in from the right and takes half of the screen, while the
results list shrinks to fit beside it and stays fully usable. Each pin is one
intersection and shows only its name and the number of matching clips; the
clips themselves are watched in the results list.

The drawer stays open when you run a new search or select another query, and
pins update in place. Watched queries that receive new clips update the pin
counts without resetting your pan or zoom.

## How It Works

1. Clips are uploaded to VSS with one tag, the camera name, prefixed by the
   intersection id, for example `intersection_1-camera2`.
2. `pipeline-manager` serves the list of intersections (id, label, latitude,
   longitude, cameras, status) at `GET /manager/geo/intersections`. It reads the
   list from an intersections API (`GEO_API_URL`), caches it, and falls back to a
   JSON file.
3. The UI assigns each search result to an intersection from its tag:
   - a tag listed under an intersection's `cameras` belongs to that intersection;
   - otherwise the part before `-cameraN` is the intersection id;
   - otherwise, a tag equal to an intersection id belongs to that intersection.
4. Results whose tags match no intersection (for example plain `camera1`) are
   listed in an "unmapped" notice, so they are never silently dropped.

The **Map View** button is shown only when the feature is enabled and at least
one intersection is known.

## Configuration

### Enabling the feature

Map View is disabled by default. With Docker Compose, export the flag before
starting; with Helm, set `feature.map: "FEATURE_ON"` in the `vss-ui` chart values:

```bash
export APP_MAP_FEATURE=FEATURE_ON
```

### Intersection source

| Variable (pipeline-manager) | Default                              | Description                                                                              |
| --------------------------- | ------------------------------------ | ---------------------------------------------------------------------------------------- |
| `GEO_API_URL`               | empty                                | Full URL of an intersections API, e.g. `http://<host>:<port>/api/v1/intersections`.      |
| `GEO_FALLBACK_FILE`         | `/app/config/geo-intersections.json` | Used when `GEO_API_URL` is empty or the API has never answered.                          |
| `GEO_REFRESH_MS`            | `60000`                              | How long the API response is cached.                                                     |
| `GEO_TIMEOUT_MS`            | `3000`                               | Timeout for each API request.                                                            |

If the API stops answering after a successful call, the last known intersections
are kept and the map shows "Intersection locations may be out of date".

With Docker Compose, export the variables before starting. The API host must be
reachable from the `pipeline-manager` container (use the host IP, not
`localhost`) and, behind a proxy, listed in `no_proxy`:

```bash
export GEO_API_URL=http://<host>:<port>/api/v1/intersections
export no_proxy="${no_proxy},<host>"
source setup.sh --search
curl http://<host>:12345/manager/geo/intersections
```

To use a fallback file from another path, set `GEO_INTERSECTIONS_FILE` to the
host path before starting.

With Helm, set `pipelinemanager.geo.apiUrl` and, optionally, the fallback under
`pipelinemanager.geo.intersections` in the parent chart values. The chart
renders the fallback into a ConfigMap and restarts `pipeline-manager` when it
changes.

### Intersections API contract

`GET /api/v1/intersections` returns intersections keyed by intersection id.
The id must equal the camera tag prefix of the uploaded clips (`intersection_1`,
`intersection_2`, ...).

```json
{
  "version": 1,
  "intersections": {
    "intersection_1": {
      "label": "Main St & 5th Ave",
      "lat": 37.51358,
      "lon": -122.25591,
      "cameras": {
        "intersection_1-camera1": { "direction": "south" },
        "intersection_1-camera2": { "direction": "west" },
        "intersection_1-camera3": { "direction": "north" },
        "intersection_1-camera4": { "direction": "east" }
      },
      "status": { "level": "NORMAL", "density": 6 }
    }
  }
}
```

| Field                        | Required | Notes                                                                                 |
| ---------------------------- | -------- | ------------------------------------------------------------------------------------- |
| `intersections.<id>`         | Yes      | Letters, digits, `_`, `.`, `-`. Must match the camera tag prefix (`intersection_1`, `intersection_2`, ...). |
| `lat`, `lon`                 | Yes      | Decimal degrees; latitude within ±85.0511, longitude within ±180. Invalid entries are dropped. |
| `label`                      | No       | Display name; defaults to the id.                                                     |
| `cameras.<tag>`              | No       | Exact camera tags with optional `label` and `direction`.                              |
| `status.level`               | No       | `NORMAL`, `MODERATE` or `HIGH`; colours the pin's status dot.                         |

The fallback file `config/geo-intersections.json` uses the same format.

### Map tiles

The map uses OpenStreetMap tiles by default. To use another tile server (for
example an internal server in an air-gapped lab), set `MAP_TILE_URL` before
starting (Compose) or `mapTileUrl` in the `vss-ui` chart values:

```bash
export MAP_TILE_URL='http://tiles.example.lab/{z}/{x}/{y}.png'
```

Without tile access the background stays grey, but pins are still placed
correctly relative to each other.

## Troubleshooting

| Symptom                                 | Check                                                                                                                                              |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| No **Map View** button                  | `APP_MAP_FEATURE` is not `FEATURE_ON`, or `curl /manager/geo/intersections` returns no intersections; check `GEO_API_URL` and the fallback file.     |
| `"source": "fallback", "stale": true`   | The intersections API is unreachable from `pipeline-manager`: host IP vs `localhost`, `no_proxy`, published port.                                  |
| Map opens but shows the unmapped notice | Result tags have no intersection prefix (clips tagged only `camera1`..`camera4` cannot be placed), or the prefix differs from the intersection ids. |
| Only some intersections are pinned      | Search returns at most the selected Top-K results; increase it or filter by tag.                                                                   |
| Grey map background                     | Tile server blocked; set `MAP_TILE_URL`.                                                                                                           |
