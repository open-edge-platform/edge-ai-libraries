// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { buildIntersectionMarkers, unmappedResultCount, unmappedTags } from '../components/MapView/intersectionMarkers';
import { buildTagIndex, IntersectionInfo } from '../redux/geo/geo';
import { SearchResult } from '../redux/search/search';
import { getSearchResultTags } from '../redux/search/searchResult';
import { createSearchResult } from './testUtils';

const makeResult = (overrides: {
  videoId: string;
  relevanceScore?: number;
  timestamp?: number;
  metadataTags?: string;
  videoMetadataTags?: string[];
  videoTags?: string[];
}): SearchResult =>
  createSearchResult({
    id: `${overrides.videoId}-${overrides.timestamp ?? 0}`,
    metadata: {
      id: overrides.videoId,
      video_id: overrides.videoId,
      timestamp: overrides.timestamp ?? 0,
      relevance_score: overrides.relevanceScore ?? 0,
      tags: overrides.metadataTags ?? '',
      ...(overrides.videoMetadataTags ? { video_metadata: { tags: overrides.videoMetadataTags } } : {}),
    },
    video: {
      videoId: overrides.videoId,
      name: overrides.videoId,
      url: `${overrides.videoId}.mp4`,
      tags: overrides.videoTags ?? [],
    },
  });

const intersections: Record<string, IntersectionInfo> = {
  intersection_1: {
    label: 'Main St & 5th Ave',
    lat: 37.51358,
    lon: -122.25591,
    cameras: {
      'intersection_1-camera1': { direction: 'south' },
      'intersection_1-camera2': { label: 'West approach', direction: 'west' },
    },
    status: { level: 'HIGH', density: 14 },
  },
  intersection_2: { label: 'Broadway', lat: 37.5391, lon: -122.30871, cameras: {} },
};
const tagIndex = buildTagIndex(intersections);

describe('getSearchResultTags', () => {
  it('reads and de-duplicates tags from every supported shape', () => {
    const result = makeResult({
      videoId: 'v1',
      metadataTags: 'intersection_1-camera1, intersection_1-camera2 , ',
      videoMetadataTags: ['intersection_1-camera1'],
      videoTags: ['intersection_2-camera1'],
    });
    expect(getSearchResultTags(result).sort()).toEqual([
      'intersection_1-camera1',
      'intersection_1-camera2',
      'intersection_2-camera1',
    ]);
  });
});

describe('buildIntersectionMarkers', () => {
  it('returns no markers without results or without intersections', () => {
    expect(buildIntersectionMarkers([], intersections, tagIndex)).toEqual([]);
    expect(buildIntersectionMarkers(null, intersections, tagIndex)).toEqual([]);
    expect(
      buildIntersectionMarkers([makeResult({ videoId: 'v1', metadataTags: 'intersection_1-camera1' })], {}, new Map()),
    ).toEqual([]);
  });

  it('groups results into one marker per intersection with per-camera groups', () => {
    const results = [
      makeResult({ videoId: 'v1', metadataTags: 'intersection_1-camera1', relevanceScore: 0.3 }),
      makeResult({ videoId: 'v2', metadataTags: 'intersection_1-camera2', relevanceScore: 0.9 }),
      makeResult({ videoId: 'v3', metadataTags: 'intersection_1-camera2', relevanceScore: 0.5 }),
      makeResult({ videoId: 'v4', metadataTags: 'intersection_2-camera4', relevanceScore: 0.7 }),
      makeResult({ videoId: 'v5', metadataTags: 'intersection_2-camera1', relevanceScore: 0.8 }),
    ];

    const markers = buildIntersectionMarkers(results, intersections, tagIndex);
    expect(markers.map((m) => m.id).sort()).toEqual(['intersection_1', 'intersection_2']);

    const intersection1 = markers.find((m) => m.id === 'intersection_1')!;
    expect(intersection1).toMatchObject({
      label: 'Main St & 5th Ave',
      lat: 37.51358,
      lon: -122.25591,
      status: { level: 'HIGH', density: 14 },
    });
    expect(intersection1.resultIndices).toEqual([1, 2, 0]);
    expect(intersection1.cameras).toEqual([
      { tag: 'intersection_1-camera1', label: 'intersection_1-camera1', direction: 'south', resultIndices: [0] },
      { tag: 'intersection_1-camera2', label: 'West approach', direction: 'west', resultIndices: [1, 2] },
    ]);

    const intersection2 = markers.find((m) => m.id === 'intersection_2')!;
    expect(intersection2.resultIndices).toEqual([4, 3]);
    expect(intersection2.cameras.map((c) => c.tag)).toEqual(['intersection_2-camera1', 'intersection_2-camera4']);
  });

  it('counts the same clip moment once but keeps different timestamps of one video', () => {
    const results = [
      makeResult({
        videoId: 'v1',
        timestamp: 5,
        metadataTags: 'intersection_1-camera1',
        videoTags: ['intersection_1-camera1'],
      }),
      makeResult({ videoId: 'v1', timestamp: 5, metadataTags: 'intersection_1-camera1' }),
      makeResult({ videoId: 'v1', timestamp: 9, metadataTags: 'intersection_1-camera1' }),
    ];

    const [marker] = buildIntersectionMarkers(results, intersections, tagIndex);
    expect(marker.resultIndices).toHaveLength(2);
  });

  it('places a result on every intersection its tags resolve to', () => {
    const results = [makeResult({ videoId: 'v1', metadataTags: 'intersection_1-camera1,intersection_2-camera1' })];
    const markers = buildIntersectionMarkers(results, intersections, tagIndex);
    expect(markers.map((m) => m.id).sort()).toEqual(['intersection_1', 'intersection_2']);
  });

  it('ignores tags that do not resolve to an intersection', () => {
    const results = [makeResult({ videoId: 'v1', metadataTags: 'camera1' })];
    expect(buildIntersectionMarkers(results, intersections, tagIndex)).toEqual([]);
  });
});

describe('unmappedTags', () => {
  it('returns nothing for an empty result list', () => {
    expect(unmappedTags([], intersections, tagIndex)).toEqual([]);
    expect(unmappedTags(null, intersections, tagIndex)).toEqual([]);
  });

  it('lists tags of results that cannot be placed, most frequent first', () => {
    const results = [
      makeResult({ videoId: 'v1', metadataTags: 'intersection_1-camera1' }),
      makeResult({ videoId: 'v2', metadataTags: 'camera1' }),
      makeResult({ videoId: 'v3', metadataTags: 'camera1' }),
      makeResult({ videoId: 'v4', metadataTags: 'intersection_9-camera2' }),
      makeResult({ videoId: 'v5', metadataTags: '' }),
    ];

    expect(unmappedTags(results, intersections, tagIndex)).toEqual([
      { tag: 'camera1', count: 2 },
      { tag: '', count: 1 },
      { tag: 'intersection_9-camera2', count: 1 },
    ]);
  });

  it('does not report a result with at least one mappable tag', () => {
    const results = [makeResult({ videoId: 'v1', metadataTags: 'camera1,intersection_2-camera3' })];
    expect(unmappedTags(results, intersections, tagIndex)).toEqual([]);
  });
});

describe('unmappedResultCount', () => {
  it('counts results, not tags', () => {
    const results = [
      makeResult({ videoId: 'v1', metadataTags: 'lobby,night' }),
      makeResult({ videoId: 'v2', metadataTags: 'intersection_1-camera1' }),
      makeResult({ videoId: 'v3', metadataTags: '' }),
    ];
    expect(unmappedResultCount(results, intersections, tagIndex)).toBe(2);
    expect(unmappedResultCount(null, intersections, tagIndex)).toBe(0);
  });
});
