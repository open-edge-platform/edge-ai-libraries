// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ResultSortBy, SearchResult } from './search';

const observedMs = (result: SearchResult): number | undefined => {
  if (!result?.observedAt) return undefined;
  const ms = Date.parse(result.observedAt);
  return Number.isFinite(ms) ? ms : undefined;
};

/**
 * Orders results for display. `relevance` keeps the server's order (already
 * ranked by score). Time orders use `observedAt`; hits without one go last in
 * their original relative order, so nothing is hidden by a sort.
 */
export const sortResults = (results: SearchResult[], sortBy: ResultSortBy = 'relevance'): SearchResult[] => {
  if (sortBy === 'relevance' || results.length < 2) return results;
  const direction = sortBy === 'oldest' ? 1 : -1;
  return results
    .map((result, index) => ({ result, index, ms: observedMs(result) }))
    .sort((a, b) => {
      if (a.ms === undefined || b.ms === undefined) {
        if (a.ms === b.ms) return a.index - b.index;
        return a.ms === undefined ? 1 : -1;
      }
      return a.ms === b.ms ? a.index - b.index : (a.ms - b.ms) * direction;
    })
    .map(({ result }) => result);
};

export interface SourceKey {
  key: string;
  isLive: boolean;
}

/**
 * Camera/video identity of a hit for "group by camera": the live stream for
 * live hits, otherwise the uploaded video.
 */
export const resultSource = (result: SearchResult): SourceKey | null => {
  if (result.streamId) return { key: `live:${result.streamId}`, isLive: true };
  const videoId = result.metadata?.video_id || result.metadata?.id;
  return videoId ? { key: `video:${videoId}`, isLive: false } : null;
};
