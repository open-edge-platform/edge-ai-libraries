// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { SearchResult } from '../../redux/search/search';
import {
  compareSearchResultsByRelevance,
  getSearchResultTags,
  getSearchResultVideoId,
} from '../../redux/search/searchResult';
import { IntersectionInfo, IntersectionStatus, resolveIntersection } from '../../redux/geo/geo';

export interface CameraGroup {
  tag: string;
  label: string;
  direction?: string;
  /** Indices into `selectedResults`, best score first. */
  resultIndices: number[];
}

export interface IntersectionMarker {
  id: string;
  label: string;
  lat: number;
  lon: number;
  status?: IntersectionStatus;
  /** All results at this intersection, best score first. `[0]` is the card's displayed result. */
  resultIndices: number[];
  cameras: CameraGroup[];
}

export interface UnmappedTag {
  tag: string;
  count: number;
}

/** Same clip moment counted once; different timestamps of one video are distinct hits, as in the list view. */
const hitKey = (result: SearchResult, index: number): string => {
  const videoId = getSearchResultVideoId(result);
  const timestamp = result.metadata?.timestamp;
  return videoId ? `${videoId}@${timestamp ?? index}` : `#${index}`;
};

export const buildIntersectionMarkers = (
  results: SearchResult[] | null | undefined,
  intersections: Record<string, IntersectionInfo>,
  tagIndex: Map<string, string>,
): IntersectionMarker[] => {
  if (!results || results.length === 0 || Object.keys(intersections).length === 0) return [];

  const buckets = new Map<string, { indices: number[]; seen: Set<string>; cameras: Map<string, number[]> }>();

  results.forEach((result, index) => {
    const key = hitKey(result, index);
    getSearchResultTags(result).forEach((tag) => {
      const id = resolveIntersection(tag, intersections, tagIndex);
      if (!id) return;

      let bucket = buckets.get(id);
      if (!bucket) {
        bucket = { indices: [], seen: new Set(), cameras: new Map() };
        buckets.set(id, bucket);
      }
      if (bucket.seen.has(key)) return;
      bucket.seen.add(key);
      bucket.indices.push(index);
      bucket.cameras.set(tag, [...(bucket.cameras.get(tag) ?? []), index]);
    });
  });

  const byRelevance = (a: number, b: number) => compareSearchResultsByRelevance(results[a], results[b]);

  return [...buckets.entries()].map(([id, bucket]) => {
    const info = intersections[id];
    return {
      id,
      label: info.label,
      lat: info.lat,
      lon: info.lon,
      status: info.status,
      resultIndices: [...bucket.indices].sort(byRelevance),
      cameras: [...bucket.cameras.entries()]
        .map(([tag, indices]) => ({
          tag,
          label: info.cameras[tag]?.label ?? tag,
          direction: info.cameras[tag]?.direction,
          resultIndices: [...indices].sort(byRelevance),
        }))
        .sort((a, b) => a.tag.localeCompare(b.tag)),
    };
  });
};

/** Tags of results that could not be placed on any intersection, with how many results carry each. */
export const unmappedTags = (
  results: SearchResult[] | null | undefined,
  intersections: Record<string, IntersectionInfo>,
  tagIndex: Map<string, string>,
): UnmappedTag[] => {
  if (!results || results.length === 0) return [];

  const counts = new Map<string, number>();
  results.forEach((result) => {
    const tags = getSearchResultTags(result);
    if (tags.some((tag) => resolveIntersection(tag, intersections, tagIndex))) return;
    const labels = tags.length > 0 ? tags : [''];
    labels.forEach((tag) => counts.set(tag, (counts.get(tag) ?? 0) + 1));
  });

  return [...counts.entries()]
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag));
};
