// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Video } from '../video/video';

export type TimeFilterUnit = 'minutes' | 'hours' | 'days' | 'weeks';

export interface TimeFilterSelection {
  value?: number;
  unit?: TimeFilterUnit;
  start?: string;
  end?: string;
  source?: string;
}

export interface SearchQueryDTO {
  query?: string;
  image?: string;
  tags?: string;
  timeFilter?: TimeFilterSelection | null;
  /** Minimum peak score (0-1); 0 disables the filter. */
  minPeakScore?: number;
}

export interface SearchShimQuery {
  query_id: string;
  query: string;
  tags?: string[];
}
export interface SearchResultRO {
  results: SearchResultBody[];
}
export interface SearchResultBody {
  query_id: string;
  results: SearchResult[];
}

export interface ScoreBreakdown {
  score: number;
  raw_score?: number;
  raw_score_min?: number;
  raw_score_max?: number;
  max_frame_score?: number;
  top_n_avg_score?: number;
  top_n_frame_count?: number;
  avg_frame_score?: number;
  quality_score?: number;
  frame_count?: number;
  contextual_weight?: number;
  contextual_boost_factor?: number;
  contextual_sigma_seconds?: number;
  segment_best_timestamp?: number | null;
  global_peak_timestamp?: number | null;
}

export interface SearchResult {
  id: string | null;
  metadata: {
    bucket_name: string;
    clip_duration: number;
    tags: string;
    date: string;
    date_time: string;
    day: number;
    fps: number;
    frames_in_clip: number;
    hours: number;
    id: string;
    interval_num: number;
    minutes: number;
    month: number;
    seconds: number;
    time: string;
    timestamp: number;
    total_frames: number;
    video: string;
    video_id: string;
    video_path: string;
    video_rel_url: string;
    video_remote_path: string;
    video_url: string;
    year: number;
    relevance_score: number;
    score_breakdown?: ScoreBreakdown;
  };
  page_content: string;
  type: string;
  video: Video;
  /**
   * Wall-clock time (ISO-8601) of the hit's peak frame, set by Pipeline Manager:
   * capture time for live hits, upload time plus offset for uploaded videos.
   */
  observedAt?: string;
  /** Basis of `observedAt`: live capture time or upload time. */
  timeSource?: 'live' | 'upload';
  /** Live stream (camera) id; absent for uploaded videos. */
  streamId?: string;
}

/** Result ordering: by relevance (server order) or by `observedAt`. */
export type ResultSortBy = 'relevance' | 'newest' | 'oldest';

/** Result grouping: flat list, by tag, or by camera/video source. */
export type ResultGroupBy = 'none' | 'tag' | 'camera';

export enum SearchQueryStatus {
  IDLE = 'idle',
  RUNNING = 'running',
  ERROR = 'error',
}

export interface SearchQuery {
  dbId?: number;
  queryId: string;
  query: string;
  // Query image (base64/data URL) for image-based searches; empty for text queries.
  image?: string | null;
  watch: boolean;
  results: SearchResult[];
  queryStatus: SearchQueryStatus;
  tags: string[];
  timeFilter?: TimeFilterSelection | null;
  /** Minimum peak score the query searches with; 0 = no filtering. */
  minPeakScore?: number | null;
  createdAt: string;
  updatedAt: string;
  errorMessage?: string;
  lastRefreshedAt?: string | null;
}

export interface SearchQueryUI extends SearchQuery {
  topK: number;
  /**
   * Per-query result grouping. Must not leak across queries. Optional on
   * construction; reads treat a missing value as `'none'`.
   */
  groupBy?: ResultGroupBy;
  /** Per-query result ordering; reads treat a missing value as `'relevance'`. */
  sortBy?: ResultSortBy;
}

/**
 * Auto-refresh settings for watched ("checked") queries, as resolved by the
 * pipeline manager. Watched queries are refreshed on this cadence only when new
 * embeddings have been indexed since the previous refresh.
 */
export interface SearchRefreshConfig {
  enabled: boolean;
  intervalMs: number;
  quietPeriodMs: number;
  batchSize: number;
  minQueryIntervalMs: number;
  maxQueriesPerTick: number;
}

/** Search settings resolved by the pipeline manager (`GET /search/config`). */
export interface SearchConfig {
  /** Default minimum peak score (SEARCH_MIN_PEAK_SCORE); 0 = filter off. */
  minPeakScoreDefault: number;
}

export interface SearchState {
  searchQueries: SearchQueryUI[];
  suggestedTags: string[];
  unreads: string[];
  selectedQuery: string | null;
  triggerLoad: boolean;
  refreshConfig?: SearchRefreshConfig | null;
  searchConfig?: SearchConfig | null;
}
