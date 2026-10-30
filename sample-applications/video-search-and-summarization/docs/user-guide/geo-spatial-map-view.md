<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Geo Spatial Map View

Geo Spatial Map View shows video search results as pins on a map. Each pin is one
location and shows how many matching clips were recorded there. Select
**Map View** in the search results header to open the map beside the results.

## Enable

Geo Spatial Map View is disabled by default. Enable it before starting VSS:

```bash
export APP_MAP_FEATURE=FEATURE_ON
source setup.sh --search
```

With Helm, set `feature.map: "FEATURE_ON"` in the `vss-ui` chart values.

## Define Locations

Edit the locations (id, label, latitude, longitude, cameras) in
[`config/geo-intersections.json`](../../config/geo-intersections.json).

A search result is pinned to a location when its video tag is the location id
itself or starts with `<location id>-` (for example `intersection_1-camera2` or
`intersection_1-crosswalk`). To map other tags, list them under the location's
`cameras`. Results
whose tags match no location are not pinned; a notice at the top of the map
shows how many.

VSS reloads the file automatically; changes appear on the map within two
minutes. To use a file from another path, set `GEO_INTERSECTIONS_FILE` before
starting. With Helm, add the locations under `pipelinemanager.geo.intersections`.

> **Note:** If a sample application provides a locations API, export its URL
> before starting VSS, for example
> `export GEO_API_URL=http://<host>:<port>/api/v1/intersections`
> (with Helm, set `pipelinemanager.geo.apiUrl`). VSS then reads locations from
> the API and falls back to the file while the API is unreachable.

## Troubleshooting

| Symptom                 | Check                                                                                                                      |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| No **Map View** button  | `APP_MAP_FEATURE` is `FEATURE_ON`, and `curl http://<host>:12345/manager/geo/intersections` returns at least one location. |
| "Not on the map" notice | Those results' video tags do not match any location id.                                                                    |
| Grey map background     | The map loads OpenStreetMap tiles and needs internet access; set `MAP_TILE_URL` to use another tile server.                |
