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
  query: string;
  tags?: string;
  timeFilter?: TimeFilterSelection | null;
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
  };
  page_content: string;
  type: string;
  video: Video;
}

export enum SearchQueryStatus {
  IDLE = 'idle',
  RUNNING = 'running',
  ERROR = 'error',
}

export interface SearchQuery {
  dbId?: number;
  queryId: string;
  query: string;
  watch: boolean;
  results: SearchResult[];
  queryStatus: SearchQueryStatus;
  tags: string[];
  timeFilter?: TimeFilterSelection | null;
  createdAt: string;
  updatedAt: string;
  errorMessage?: string;
}

export interface SearchQueryUI extends SearchQuery {
  topK: number;
}

export interface SearchState {
  searchQueries: SearchQueryUI[];
  suggestedTags: string[];
  unreads: string[];
  selectedQuery: string | null;
  triggerLoad: boolean;
}
