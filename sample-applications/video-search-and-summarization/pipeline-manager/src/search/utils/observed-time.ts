// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { ObservedTimeSource, SearchResult } from '../model/search.model';
import { VideoEntity } from 'src/video-upload/models/video.entity';

export interface ObservedTime {
  observedAt: string;
  timeSource: ObservedTimeSource;
}

// Live segments are named after the epoch second their recording started,
// e.g. `live-streams/<streamId>/segments/1790655530.mp4`.
const SEGMENT_EPOCH_RE = /(?:^|\/)(\d{9,11})(?:\.\d+)?\.mp4$/;

const finiteNumber = (value: unknown): number | undefined =>
  typeof value === 'number' && Number.isFinite(value) ? value : undefined;

const parseEpochMs = (value: unknown): number | undefined => {
  if (typeof value !== 'string' || !value.trim()) {
    return undefined;
  }
  // Naive timestamps (no zone) are UTC, matching how dataprep writes them.
  const text = /(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
  const ms = Date.parse(text);
  return Number.isFinite(ms) ? ms : undefined;
};

/** Seconds into the addressed media (file for uploads, segment for live). */
const frameOffsetSeconds = (metadata: SearchResult['metadata']): number =>
  finiteNumber(metadata?.best_frame_info?.timestamp) ??
  finiteNumber(metadata?.seek_timestamp) ??
  finiteNumber(metadata?.segment_start) ??
  0;

/**
 * Wall-clock time of a search hit's peak frame.
 *
 * - Live hits use the segment's recording start (from its file name, falling
 *   back to the segment row's `created_at`) plus the frame offset.
 * - Uploaded videos use the time the video was uploaded to VSS
 *   (`VideoEntity.createdAt`) plus the frame offset. Embedding `created_at`
 *   is deliberately not used: it is the embed time, which moves on re-index
 *   and copies.
 */
export const resolveObservedTime = (
  result: SearchResult,
  video?: VideoEntity,
): ObservedTime | undefined => {
  const metadata = result?.metadata;
  const info = metadata?.best_frame_info;
  const offsetMs = frameOffsetSeconds(metadata) * 1000;

  if (info?.is_live) {
    const match = SEGMENT_EPOCH_RE.exec(String(info.media_path ?? ''));
    const loose = metadata as unknown as Record<string, unknown>;
    const startMs = match
      ? Number(match[1]) * 1000
      : parseEpochMs(
          (loose.video_metadata as Record<string, unknown> | undefined)
            ?.created_at ?? loose.created_at,
        );
    return startMs === undefined
      ? undefined
      : {
          observedAt: new Date(startMs + offsetMs).toISOString(),
          timeSource: 'live',
        };
  }

  const uploadMs = parseEpochMs(video?.createdAt);
  return uploadMs === undefined
    ? undefined
    : {
        observedAt: new Date(uploadMs + offsetMs).toISOString(),
        timeSource: 'upload',
      };
};
