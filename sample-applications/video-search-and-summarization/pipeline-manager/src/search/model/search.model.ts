// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { VideoEntity } from 'src/video-upload/models/video.entity';

export type TimeFilterUnit = 'minutes' | 'hours' | 'days' | 'weeks';

export class TimeFilterSelection {
  @ApiPropertyOptional({ description: 'Relative time value', example: 7 })
  value?: number;

  @ApiPropertyOptional({
    enum: ['minutes', 'hours', 'days', 'weeks'],
    description: 'Time unit for relative filter',
  })
  unit?: TimeFilterUnit;

  @ApiPropertyOptional({
    description: 'Start date (ISO 8601)',
    example: '2025-01-01T00:00:00Z',
  })
  start?: string;

  @ApiPropertyOptional({
    description: 'End date (ISO 8601)',
    example: '2025-12-31T23:59:59Z',
  })
  end?: string;

  @ApiPropertyOptional({ description: 'Filter source identifier' })
  source?: string;
}

export class SearchQueryDTO {
  @ApiPropertyOptional({
    description:
      'Non-blank text search query. Provide either `query` or `image` (not both).',
    example: 'person walking',
  })
  query?: string;

  @ApiPropertyOptional({
    description:
      'Query image as a base64 string or data URL, for image-based search. ' +
      'Provide either `query` or `image` (not both). Only supported in ' +
      'frame-embedding modes (--search/--dual).',
  })
  image?: string;

  @ApiPropertyOptional({
    description: 'Comma-separated tags to filter by',
    example: 'outdoor,daytime',
  })
  tags?: string;

  @ApiPropertyOptional({
    type: TimeFilterSelection,
    description: 'Time range filter',
    nullable: true,
  })
  timeFilter?: TimeFilterSelection | null;
}

export class RefetchBodyDTO {
  @ApiPropertyOptional({
    type: TimeFilterSelection,
    description: 'Optional time filter override',
  })
  timeFilter?: TimeFilterSelection;
}

export class WatchBodyDTO {
  @ApiProperty({ description: 'Whether to watch this query' })
  watch: boolean;
}

export enum SearchQueryStatus {
  IDLE = 'idle',
  RUNNING = 'running',
  ERROR = 'error',
}

export interface SearchShimQuery {
  query_id: string;
  query?: string;
  image_base64?: string;
  tags?: string[];
  time_filter?: { start: string; end: string };
}

export interface SearchResultRO {
  results: SearchResultBody[];
}
export interface SearchResultBody {
  query_id: string;
  results: SearchResult[];
  error?: string;
}

/**
 * Addressing + provenance for the exact peak-scoring frame of a search hit.
 *
 * Produced by search-ms and passed through unchanged. A downstream agent takes
 * these fields straight to `GET /manager/frames` to fetch the actual pixels of
 * the frame that matched (to hand to a VLM, etc.).
 */
export interface BestFrameInfo {
  /** Uploaded video_id or live stream_id — the `video_id` for GET /manager/frames. */
  video_id: string;
  /** Bucket/top-level directory holding the media. */
  bucket_name: string;
  /**
   * Seconds from the start of the addressed media to the peak frame. Pass this
   * (NOT the segment-level `seek_timestamp`) as `timestamp` to GET /manager/frames.
   */
  timestamp: number;
  /** Frame index of the peak frame within its source. */
  frame_number: number;
  /** 'full_frame' or 'detected_crop' — how the peak frame was embedded. */
  frame_type: string;
  /** Detector confidence when the peak came from a detected crop; else null. */
  detection_confidence?: number | null;
  /** Detected object label when the peak came from a detected crop; else null. */
  detected_label?: string | null;
  /** True when the peak frame is a detected-object crop rather than a full frame. */
  is_detected_crop: boolean;
  /** Index of the crop among a frame's detections; null for full frames. */
  crop_index?: number | null;
  /**
   * Pixel box [x1, y1, x2, y2] of the detected crop. Supply to GET /manager/frames
   * with variant='crop' to get just the region; omit for the full frame.
   */
  crop_bbox?: number[] | null;
  /** True for live-stream hits, whose pixels live in a per-stream segment. */
  is_live: boolean;
  /**
   * Relative object path of the segment holding a live frame, e.g.
   * 'segments/1790655530.mp4'. REQUIRED as `media_path` for live frames.
   */
  media_path?: string | null;
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
    // Present on aggregated (clip-level) results returned by the search
    // backend. These, not `id`/`interval_num`, are what actually identify
    // which moment of a video matched.
    seek_timestamp?: number;
    segment_start?: number;
    segment_end?: number;
    // Addressing for the exact peak-scoring frame of this hit. Pass-through
    // from search-ms; feed these fields to GET /manager/frames.
    best_frame_info?: BestFrameInfo;
  };
  video?: VideoEntity;
  page_content: string;
  type: string;
}

export interface SearchQuery {
  dbId?: number;
  queryId: string;
  query: string;
  image?: string | null;
  watch: boolean;
  results: SearchResult[];
  queryStatus: SearchQueryStatus;
  tags: string[];
  timeFilter?: TimeFilterSelection | null;
  createdAt: string;
  updatedAt: string;
  errorMessage?: string;
  lastRefreshedAt?: string | null;
  resultsFingerprint?: string | null;
}
