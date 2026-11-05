// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { WEB_MERCATOR_MAX_LATITUDE } from '../../utils/webMercator';

export interface IntersectionCamera {
  label?: string;
  direction?: string;
}

export interface IntersectionStatus {
  level?: string;
  density?: number;
  incident?: string;
  updated_at?: string;
}

export interface IntersectionInfo {
  label: string;
  lat: number;
  lon: number;
  cameras: Record<string, IntersectionCamera>;
  status?: IntersectionStatus;
}

export type GeoSource = 'geo-api' | 'fallback' | 'none';

/** Body of `GET /manager/geo/intersections`. */
export interface GeoIntersectionsResponse {
  source: GeoSource;
  stale: boolean;
  fetchedAt: string | null;
  intersections: Record<string, IntersectionInfo>;
}

export interface GeoState {
  intersections: Record<string, IntersectionInfo>;
  source: GeoSource;
  stale: boolean;
  loaded: boolean;
}

/** Coordinates must be finite and within the Web Mercator tile-grid domain. */
export const isValidLatLon = (lat: unknown, lon: unknown): boolean =>
  typeof lat === 'number' &&
  Number.isFinite(lat) &&
  Math.abs(lat) <= WEB_MERCATOR_MAX_LATITUDE &&
  typeof lon === 'number' &&
  Number.isFinite(lon) &&
  Math.abs(lon) <= 180;

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const optionalString = (value: unknown): string | undefined =>
  typeof value === 'string' && value.trim() ? value.trim() : undefined;

/**
 * Defensive parse of the backend response. The backend already validates, but
 * the UI must still survive an unexpected body (e.g. an HTML error page).
 */
export const parseGeoResponse = (body: unknown): Omit<GeoState, 'loaded'> => {
  if (!isObject(body)) return { intersections: {}, source: 'none', stale: false };

  const intersections: Record<string, IntersectionInfo> = {};
  if (isObject(body.intersections)) {
    for (const [id, raw] of Object.entries(body.intersections)) {
      if (!isObject(raw) || !isValidLatLon(raw.lat, raw.lon)) continue;
      const cameras: Record<string, IntersectionCamera> = {};
      if (isObject(raw.cameras)) {
        for (const [tag, camera] of Object.entries(raw.cameras)) {
          const cam = isObject(camera) ? camera : {};
          cameras[tag] = { label: optionalString(cam.label), direction: optionalString(cam.direction) };
        }
      }
      intersections[id] = {
        label: optionalString(raw.label) ?? id,
        lat: raw.lat as number,
        lon: raw.lon as number,
        cameras,
        status: isObject(raw.status) ? (raw.status as IntersectionStatus) : undefined,
      };
    }
  }

  const source: GeoSource = body.source === 'geo-api' || body.source === 'fallback' ? body.source : 'none';
  return { intersections, source, stale: body.stale === true };
};

/** Map of camera tag -> intersection id for cameras explicitly listed under an intersection. */
export const buildTagIndex = (intersections: Record<string, IntersectionInfo>): Map<string, string> => {
  const index = new Map<string, string>();
  Object.entries(intersections).forEach(([id, info]) => {
    Object.keys(info.cameras).forEach((tag) => index.set(tag, id));
  });
  return index;
};

/** Resolve a tag to its intersection id: listed camera, then the tag itself, then the longest `<id>-` prefix. */
export const resolveIntersection = (
  tag: string,
  intersections: Record<string, IntersectionInfo>,
  tagIndex: Map<string, string>,
): string | null => {
  // Own-property check: tags such as "constructor" must not match inherited Object members.
  const isKnown = (id: string) => Object.prototype.hasOwnProperty.call(intersections, id);
  const listed = tagIndex.get(tag);
  if (listed) return listed;
  if (isKnown(tag)) return tag;
  let match: string | null = null;
  for (const id of Object.keys(intersections)) {
    if (tag.startsWith(`${id}-`) && (!match || id.length > match.length)) match = id;
  }
  return match;
};
