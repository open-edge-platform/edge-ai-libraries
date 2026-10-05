// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { VideoEntity } from 'src/video-upload/models/video.entity';

export type TimeFilterUnit = 'minutes' | 'hours' | 'days' | 'weeks';

export class TimeFilterSelection {
  @ApiPropertyOptional({ description: 'Relative time value', example: 7 })
  value?: number;

  @ApiPropertyOptional({ enum: ['minutes', 'hours', 'days', 'weeks'], description: 'Time unit for relative filter' })
  unit?: TimeFilterUnit;

  @ApiPropertyOptional({ description: 'Start date (ISO 8601)', example: '2025-01-01T00:00:00Z' })
  start?: string;

  @ApiPropertyOptional({ description: 'End date (ISO 8601)', example: '2025-12-31T23:59:59Z' })
  end?: string;

  @ApiPropertyOptional({ description: 'Filter source identifier' })
  source?: string;
}

export class SearchQueryDTO {
  @ApiPropertyOptional({
    description:
      'Non-blank text search query. Provide exactly one of `query`, ' +
      '`image` or `imageUrl`.',
    example: 'person walking',
  })
  query?: string;

  @ApiPropertyOptional({
    description:
      'Query image as a base64 string or data URL, for image-based search. ' +
      'Provide exactly one of `query`, `image` or `imageUrl`. Only ' +
      'supported in frame-embedding modes (--search/--dual).',
  })
  image?: string;

  @ApiPropertyOptional({
    description:
      'Reference to a query image previously uploaded with ' +
      '`POST /search/images`: its `imageUrl`, `imagePath` or `imageId`. ' +
      'Any host is accepted; only the path is used. Provide exactly one of ' +
      '`query`, `image` or `imageUrl`. Only supported in frame-embedding ' +
      'modes (--search/--dual).',
    example:
      'http://192.168.1.10:12345/datastore/video-summary/search-images/3f0c1f1e-7c1b-4a8e-9a55-0d6f6c2b9e11.jpg',
  })
  imageUrl?: string;

  @ApiPropertyOptional({ description: 'Comma-separated tags to filter by', example: 'outdoor,daytime' })
  tags?: string;

  @ApiPropertyOptional({ type: TimeFilterSelection, description: 'Time range filter', nullable: true })
  timeFilter?: TimeFilterSelection | null;
}

export class RefetchBodyDTO {
  @ApiPropertyOptional({ type: TimeFilterSelection, description: 'Optional time filter override' })
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
    /**
     * Point (seconds into the video) to seek playback to, as returned by
     * the search-ms frame-to-video aggregation. Only present in
     * frame-embedding search modes (--search/--dual); older/VDMS result
     * shapes may omit it.
     */
    seek_timestamp?: number;
  };
  video?: VideoEntity;
  /**
   * Gateway-relative, directly downloadable/playable path for this hit's
   * source video, e.g. `/my-bucket/<videoId>/source.mp4`. Prefix with the
   * datastore base URL (the same host the search request itself was sent to,
   * with `/datastore` in place of `/manager`) to get a fully qualified,
   * host-reachable link. Present whenever the hit's `video_id` matches a
   * known video with object-store info; absent otherwise (e.g. the video was
   * deleted after being indexed).
   */
  videoPlaybackUrl?: string;
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
}
