// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export interface GeoCamera {
  label?: string;
  direction?: string;
}

export interface GeoStatus {
  level?: string;
  density?: number;
  incident?: string;
  updated_at?: string;
}

export interface GeoIntersection {
  label: string;
  lat: number;
  lon: number;
  cameras: Record<string, GeoCamera>;
  status?: GeoStatus;
}

export type GeoSource = 'geo-api' | 'fallback' | 'none';

export interface GeoIntersectionsRO {
  source: GeoSource;
  stale: boolean;
  fetchedAt: string | null;
  intersections: Record<string, GeoIntersection>;
}

export interface GeoConfig {
  apiUrl?: string;
  fallbackFile?: string;
  refreshMs: number;
  timeoutMs: number;
}

export const WEB_MERCATOR_MAX_LATITUDE = 85.0511287798066;
export const MAX_INTERSECTIONS = 1000;
const ID_PATTERN = /^[A-Za-z0-9_.-]+$/;

type RawObject = Record<string, unknown>;

const isObject = (value: unknown): value is RawObject =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const optionalString = (value: unknown): string | undefined =>
  typeof value === 'string' && value.trim() ? value.trim() : undefined;

export const isValidLatLon = (lat: unknown, lon: unknown): boolean =>
  typeof lat === 'number' &&
  typeof lon === 'number' &&
  Number.isFinite(lat) &&
  Number.isFinite(lon) &&
  Math.abs(lat) <= WEB_MERCATOR_MAX_LATITUDE &&
  Math.abs(lon) <= 180;

const normalizeStatus = (value: unknown): GeoStatus | undefined => {
  if (!isObject(value)) return undefined;
  const status: GeoStatus = {
    level: optionalString(value.level),
    density:
      typeof value.density === 'number' && Number.isFinite(value.density)
        ? value.density
        : undefined,
    incident: optionalString(value.incident),
    updated_at: optionalString(value.updated_at),
  };
  return Object.values(status).some((v) => v !== undefined)
    ? status
    : undefined;
};

const normalizeCameras = (value: unknown): Record<string, GeoCamera> => {
  const cameras: Record<string, GeoCamera> = {};
  if (!isObject(value)) return cameras;
  for (const [rawTag, rawCamera] of Object.entries(value)) {
    const tag = rawTag.trim();
    if (!tag) continue;
    const camera = isObject(rawCamera) ? rawCamera : {};
    cameras[tag] = {
      label: optionalString(camera.label),
      direction: optionalString(camera.direction),
    };
  }
  return cameras;
};

/**
 * Normalizes `{ intersections: { <id>: {...} } }` from the intersections API or the fallback file.
 * Invalid entries are dropped and reported via `warn`.
 */
export const normalizeIntersections = (
  raw: unknown,
  warn: (message: string) => void,
): Record<string, GeoIntersection> => {
  if (!isObject(raw) || !isObject(raw.intersections)) return {};
  const source: RawObject = raw.intersections;

  const result: Record<string, GeoIntersection> = {};
  for (const [id, value] of Object.entries(source)) {
    if (Object.keys(result).length >= MAX_INTERSECTIONS) {
      warn(`geo: more than ${MAX_INTERSECTIONS} intersections, ignoring rest`);
      break;
    }
    if (!ID_PATTERN.test(id) || !isObject(value)) {
      warn(`geo: dropping intersection with invalid id or body "${id}"`);
      continue;
    }
    if (!isValidLatLon(value.lat, value.lon)) {
      warn(`geo: dropping intersection "${id}" with invalid lat/lon`);
      continue;
    }
    result[id] = {
      label: optionalString(value.label) ?? id,
      lat: value.lat as number,
      lon: value.lon as number,
      cameras: normalizeCameras(value.cameras),
      status: normalizeStatus(value.status),
    };
  }
  return result;
};
