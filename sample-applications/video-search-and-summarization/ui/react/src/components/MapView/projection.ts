// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Web Mercator projection and viewport math for the Map View: panning, zooming
// and the tile grid, as pure functions with no DOM dependency.

import { clampWebMercatorLatitude } from '../../utils/webMercator';

export const TILE_SIZE = 256;
export const MIN_ZOOM = 0;
export const MAX_ZOOM = 19;

export interface WorldPoint {
  x: number;
  y: number;
}

export interface LonLat {
  lon: number;
  lat: number;
}

export interface MapViewport {
  center: LonLat;
  zoom: number;
  width: number;
  height: number;
}

export interface ScreenPoint {
  x: number;
  y: number;
}

export interface TileDescriptor {
  z: number;
  /** Unwrapped source-tile column, used to distinguish repeated world copies. */
  column: number;
  x: number;
  y: number;
  /** Rendered tile size in CSS pixels after scaling to the viewport zoom. */
  size: number;
  /** Screen-space top-left corner of this tile, in CSS pixels. */
  left: number;
  top: number;
}

const clamp = (value: number, min: number, max: number): number => Math.min(Math.max(value, min), max);

/** World size, in pixels, of the whole map at a given zoom level. */
export const worldSize = (zoom: number): number => TILE_SIZE * 2 ** zoom;

/**
 * Project a lon/lat pair to world pixel coordinates at a given zoom (standard
 * spherical Web Mercator, as used by OSM/Google/Bing tile schemes).
 */
export const lonLatToWorld = (lon: number, lat: number, zoom: number): WorldPoint => {
  const size = worldSize(zoom);
  const projectedLatitude = clampWebMercatorLatitude(lat);
  const sinLat = Math.sin((projectedLatitude * Math.PI) / 180);

  const x = size * (0.5 + lon / 360);
  const y = size * (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI));

  return { x, y };
};

/** Inverse of {@link lonLatToWorld}. */
export const worldToLonLat = (x: number, y: number, zoom: number): LonLat => {
  const size = worldSize(zoom);

  const lon = (x / size - 0.5) * 360;
  const n = Math.PI - (2 * Math.PI * y) / size;
  const lat = (180 / Math.PI) * Math.atan(Math.sinh(n));

  return { lon, lat };
};

/** Project a lon/lat pair to screen pixel coordinates within a given viewport. */
export const lonLatToScreen = (lon: number, lat: number, view: MapViewport): ScreenPoint => {
  const worldCenter = lonLatToWorld(view.center.lon, view.center.lat, view.zoom);
  const worldPoint = lonLatToWorld(lon, lat, view.zoom);

  return {
    x: view.width / 2 + (worldPoint.x - worldCenter.x),
    y: view.height / 2 + (worldPoint.y - worldCenter.y),
  };
};

/** Inverse of {@link lonLatToScreen}: screen pixel coordinates back to a lon/lat pair. */
export const screenToLonLat = (x: number, y: number, view: MapViewport): LonLat => {
  const worldCenter = lonLatToWorld(view.center.lon, view.center.lat, view.zoom);

  const worldX = worldCenter.x + (x - view.width / 2);
  const worldY = worldCenter.y + (y - view.height / 2);

  return worldToLonLat(worldX, worldY, view.zoom);
};

/**
 * Return the grid of raster tiles that cover the viewport (plus no extra
 * margin - callers add their own margin for culling). Raster source tiles use
 * an integer zoom and are scaled to the viewport's possibly fractional zoom,
 * keeping the raster and marker layers in the same screen-space scale.
 */
export const visibleTiles = (view: MapViewport): TileDescriptor[] => {
  const viewportZoom = clamp(view.zoom, MIN_ZOOM, MAX_ZOOM);
  const z = Math.floor(viewportZoom);
  const tileCount = 2 ** z;
  const scale = 2 ** (viewportZoom - z);
  const renderedTileSize = TILE_SIZE * scale;

  const worldCenter = lonLatToWorld(view.center.lon, view.center.lat, z);
  const visibleWorldWidth = view.width / scale;
  const visibleWorldHeight = view.height / scale;
  const topLeftWorldX = worldCenter.x - visibleWorldWidth / 2;
  const topLeftWorldY = worldCenter.y - visibleWorldHeight / 2;

  const startTileX = Math.floor(topLeftWorldX / TILE_SIZE);
  const endTileX = Math.floor((topLeftWorldX + visibleWorldWidth) / TILE_SIZE);
  const startTileY = Math.floor(topLeftWorldY / TILE_SIZE);
  const endTileY = Math.floor((topLeftWorldY + visibleWorldHeight) / TILE_SIZE);

  const tiles: TileDescriptor[] = [];

  for (let tx = startTileX; tx <= endTileX; tx++) {
    for (let ty = startTileY; ty <= endTileY; ty++) {
      // Mercator is undefined past the poles - simply drop out-of-range rows.
      if (ty < 0 || ty >= tileCount) continue;

      // Longitude wraps around the antimeridian; tile columns wrap with it.
      const wrappedX = ((tx % tileCount) + tileCount) % tileCount;

      tiles.push({
        z,
        column: tx,
        x: wrappedX,
        y: ty,
        size: renderedTileSize,
        left: (tx * TILE_SIZE - topLeftWorldX) * scale,
        top: (ty * TILE_SIZE - topLeftWorldY) * scale,
      });
    }
  }

  return tiles;
};

export interface FitBoundsResult {
  center: LonLat;
  zoom: number;
}

/**
 * Compute a viewport that frames a set of points with some padding.
 * Falls back to a fixed close-in zoom when there is only one point, or when
 * every point sits at the same coordinate (a real bounding box would divide
 * by zero there).
 */
export const fitBounds = (points: LonLat[], width: number, height: number, padding = 60): FitBoundsResult => {
  const SINGLE_POINT_ZOOM = 15;

  if (points.length === 0) {
    return { center: { lon: 0, lat: 0 }, zoom: MIN_ZOOM };
  }

  const lons = points.map((p) => p.lon);
  const lats = points.map((p) => p.lat);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);

  const fallbackCenter: LonLat = { lon: (minLon + maxLon) / 2, lat: (minLat + maxLat) / 2 };

  if (points.length === 1 || (minLon === maxLon && minLat === maxLat)) {
    return { center: fallbackCenter, zoom: SINGLE_POINT_ZOOM };
  }

  const availableWidth = Math.max(width - padding * 2, 1);
  const availableHeight = Math.max(height - padding * 2, 1);

  // Measure the bounds' world-pixel span at zoom 0, then solve for the zoom that fits it to the viewport.
  const topLeft = lonLatToWorld(minLon, maxLat, 0);
  const bottomRight = lonLatToWorld(maxLon, minLat, 0);
  const projectedCenter = worldToLonLat((topLeft.x + bottomRight.x) / 2, (topLeft.y + bottomRight.y) / 2, 0);
  const center: LonLat = { lon: fallbackCenter.lon, lat: projectedCenter.lat };
  const spanX = Math.max(Math.abs(bottomRight.x - topLeft.x), 1e-9);
  const spanY = Math.max(Math.abs(bottomRight.y - topLeft.y), 1e-9);

  const zoomX = Math.log2(availableWidth / spanX);
  const zoomY = Math.log2(availableHeight / spanY);
  const zoom = clamp(Math.min(zoomX, zoomY), MIN_ZOOM, MAX_ZOOM);

  return { center, zoom };
};
