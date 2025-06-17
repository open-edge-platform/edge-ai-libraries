// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export interface SearchQueryDTO {
  query: string;
  tags?: string[];
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
}

export interface SearchQuery {
  dbId?: number;
  queryId: string;
  query: string;
  watch: boolean;
  results: SearchResult[];
  tags: string[];
  createdAt: string;
  updatedAt: string;
}

export interface DataPrepMinioDTO {
  bucket_name: string;
  video_id: string;
  video_name: string;
  chunk_duration?: number;
  clip_duration?: number;
}

export interface DataPrepMinioRO {
  status: string;
  message: string;
}
