// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Video } from './video';

const SAFE_PATH_SEGMENT = /^[a-zA-Z0-9._-]+$/;

export interface SearchResultVideoMetadata {
  bucket_name?: string;
  video_id?: string;
  video_url?: string;
  video_rel_url?: string;
}

/** Download-API URLs that are not object-store paths and cannot be played directly. */
const DOWNLOAD_API_MARKERS = ['/videos/download?video_id=', '/v1/dataprep/media/download'];

const toObjectStorePath = (value: unknown): string | null => {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (DOWNLOAD_API_MARKERS.some((marker) => trimmed.includes(marker))) return null;
  // Anything with a query string is an API call rather than an object path.
  if (trimmed.includes('?')) return null;
  return trimmed.startsWith('/') ? trimmed : null;
};

export const resolveVideoUrl = (video?: Video | null, assetsEndpoint = ''): string | null => {
  if (!video) return null;

  if (video.dataStore?.bucket && video.url) {
    return `${assetsEndpoint}/${video.dataStore.bucket}/${video.url}`;
  }

  if (video.url) {
    return video.url;
  }

  return null;
};

/**
 * Build a direct object-store URL for a search hit.
 *
 * Going straight to the object store through the gateway's `/datastore` proxy
 * keeps HTTP range requests (and therefore seeking) working, and avoids
 * depending on the dataprep download API. The dataprep download URLs carried in
 * search metadata are rejected: the absolute form points at an internal compose
 * hostname the browser cannot reach, and the relative form is not an object path.
 *
 * Preference order:
 *  1. A metadata URL that is already an object-store path.
 *  2. A path derived from `bucket_name` + `video_id`, which is how the
 *     datastore lays objects out (`<videoId>/source.<ext>`).
 */
export const resolveSearchResultVideoUrl = (
  metadata: SearchResultVideoMetadata | null | undefined,
  assetsEndpoint = '',
): string | null => {
  const base = assetsEndpoint.replace(/\/$/, '');

  const fromMetadataPath = toObjectStorePath(metadata?.video_rel_url) ?? toObjectStorePath(metadata?.video_url);
  if (fromMetadataPath) {
    return fromMetadataPath.startsWith(base) ? fromMetadataPath : `${base}${fromMetadataPath}`;
  }

  const bucket = metadata?.bucket_name?.trim();
  const videoId = metadata?.video_id?.trim();
  if (!bucket || !videoId) return null;
  if (!SAFE_PATH_SEGMENT.test(bucket) || !SAFE_PATH_SEGMENT.test(videoId)) return null;

  return `${base}/${bucket}/${encodeURIComponent(videoId)}/source.mp4`;
};
