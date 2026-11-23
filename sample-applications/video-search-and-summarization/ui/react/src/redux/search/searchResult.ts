// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { SearchResult } from './search';

export interface SearchResultTagObject {
  tag?: string;
  name?: string;
  label?: string;
}
export type SearchResultTag = string | SearchResultTagObject;
export type SearchResultTags = string | SearchResultTag[];

/** Depending on the dataprep version, tags arrive as CSV, a list, objects, or nested under video_metadata. */
export interface SearchResultTagFields {
  tags?: SearchResultTags;
  video_metadata?: { tags?: SearchResultTags };
}

const addTag = (tags: Set<string>, value: SearchResultTag): void => {
  if (!value || (typeof value !== 'string' && typeof value !== 'object')) return;

  const candidate =
    typeof value === 'string'
      ? value
      : typeof value.tag === 'string'
        ? value.tag
        : typeof value.name === 'string'
          ? value.name
          : typeof value.label === 'string'
            ? value.label
            : '';
  const normalized = candidate.trim();
  if (normalized) tags.add(normalized);
};

const addTags = (tags: Set<string>, values: SearchResultTags | undefined): void => {
  if (typeof values === 'string') {
    values.split(',').forEach((tag) => addTag(tags, tag));
    return;
  }
  values?.forEach((tag) => addTag(tags, tag));
};

/** Return every supported search-result tag shape as trimmed, de-duplicated strings. */
export const getSearchResultTags = (result: SearchResult | null | undefined): string[] => {
  if (!result) return [];

  const tags = new Set<string>();
  const metadata = result.metadata as SearchResultTagFields | undefined;
  addTags(tags, metadata?.tags);
  addTags(tags, metadata?.video_metadata?.tags);
  addTags(tags, result.video?.tags);
  return Array.from(tags);
};

/** Resolve the stable video identity used to de-duplicate grouped results. */
export const getSearchResultVideoId = (result: SearchResult | null | undefined): string | null => {
  const candidate = result?.metadata?.video_id || result?.metadata?.id || result?.video?.videoId;
  return typeof candidate === 'string' && candidate.trim() ? candidate.trim() : null;
};

const relevanceScore = (result: SearchResult): number => {
  const score = result.metadata?.relevance_score;
  return typeof score === 'number' && Number.isFinite(score) ? score : 0;
};

/** Sort highest relevance first while treating a missing or invalid score as zero. */
export const compareSearchResultsByRelevance = (left: SearchResult, right: SearchResult): number =>
  relevanceScore(right) - relevanceScore(left);
