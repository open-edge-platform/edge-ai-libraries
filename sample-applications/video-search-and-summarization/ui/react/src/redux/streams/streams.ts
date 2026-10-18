// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { StateActionStatus } from '../summary/summary';

/** Mirrors `LiveStreamStateEnum` in multimodal-dataprep. */
export enum LiveStreamState {
  PENDING = 'pending',
  STARTING = 'starting',
  RUNNING = 'running',
  PAUSED = 'paused',
  RECONNECTING = 'reconnecting',
  ERROR = 'error',
  STOPPED = 'stopped',
}

export interface LiveStreamStats {
  frames_processed: number;
  embeddings_created: number;
  segments_stored: number;
  frames_stored: number;
  reconnect_count: number;
  last_frame_ts?: number | null;
  started_ts?: number | null;
  uptime_seconds?: number | null;
}

export interface LiveStream {
  stream_id: string;
  /** Always redacted by the backend - never carries credentials. */
  stream_url: string;
  stream_name: string;
  description?: string | null;
  state: LiveStreamState;
  bucket_name?: string | null;
  video_id?: string | null;
  sensor_id?: string | null;
  frame_interval: number;
  enable_object_detection: boolean;
  detection_confidence: number;
  tags: string[];
  stats: LiveStreamStats;
  last_error?: string | null;
  created_ts?: number | null;
  updated_ts?: number | null;
}

export interface LiveStreamListRO {
  count: number;
  streams: LiveStream[];
}

export interface LiveStreamRO {
  stream: LiveStream;
}

/**
 * Create payload.
 *
 * `stream_url` may carry credentials, so this value must never become a Redux
 * action argument - see `streamsApi.createStream`.
 */
export interface LiveStreamCreatePayload {
  stream_url: string;
  stream_name?: string;
  description?: string;
  sensor_id?: string;
  frame_interval?: number;
  enable_object_detection?: boolean;
  detection_confidence?: number;
  tags?: string[];
  start?: boolean;
}

/** Update payload. `stream_url` is absent because the API cannot change it. */
export interface LiveStreamUpdatePayload {
  stream_name?: string;
  description?: string;
  frame_interval?: number;
  enable_object_detection?: boolean;
  detection_confidence?: number;
  tags?: string[];
  state?: LiveStreamState.RUNNING | LiveStreamState.PAUSED;
}

export interface LiveStreamPurgeOptions {
  purge_embeddings?: boolean;
  purge_media?: boolean;
}

export interface LiveStreamFilters {
  state?: LiveStreamState | '';
  tag?: string;
}

export interface StreamsState {
  streams: LiveStream[];
  status: StateActionStatus;
  /** Last load error, surfaced in the modal rather than as a toast. */
  error: string | null;
  filters: LiveStreamFilters;
}
