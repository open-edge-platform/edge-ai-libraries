// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { RefObject, useEffect } from 'react';

const MAX_RETRIES = 4;
const RETRY_BASE_MS = 800;

/**
 * Drives a `<video>` element's load + seek, with bounded auto-retry on load
 * failure.
 *
 * The seek is driven by `loadedmetadata` because `load()` resets `currentTime`
 * and duration is unknown until the container is parsed.
 *
 * Retry rationale: a single failed fetch (a transient 404/5xx from object
 * storage, a presigned URL that is not ready yet, or a dropped connection)
 * otherwise leaves the tile black forever, because the effect dependencies
 * (`videoUrl` / `seekTime`) do not change, so nothing re-issues `load()`. On an
 * `error` we retry `load()` up to `MAX_RETRIES` times with linear backoff. A
 * successful load resets the budget so later transient drops are retried again.
 */
export const useSeekableVideo = (
  videoRef: RefObject<HTMLVideoElement | null>,
  videoUrl: string | null | undefined,
  seekTime: number,
): void => {
  useEffect(() => {
    const videoEl = videoRef.current;
    if (!videoEl || !videoUrl) return undefined;

    let retries = 0;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let disposed = false;

    const clearRetry = () => {
      if (retryTimer !== undefined) {
        clearTimeout(retryTimer);
        retryTimer = undefined;
      }
    };

    const seekToTimestamp = () => {
      if (seekTime > 0 && Number.isFinite(videoEl.duration)) {
        videoEl.currentTime = Math.min(seekTime, Math.max(videoEl.duration - 0.1, 0));
      }
    };

    const handleLoaded = () => {
      retries = 0;
      seekToTimestamp();
    };

    const handleError = () => {
      if (disposed || retries >= MAX_RETRIES) return;
      retries += 1;
      clearRetry();
      retryTimer = setTimeout(() => {
        if (disposed) return;
        videoEl.load();
      }, RETRY_BASE_MS * retries);
    };

    videoEl.addEventListener('loadedmetadata', handleLoaded);
    // Capture phase so errors dispatched at the child <source> element (which do
    // not bubble) are still observed on the <video> ancestor.
    videoEl.addEventListener('error', handleError, true);
    videoEl.load();

    return () => {
      disposed = true;
      clearRetry();
      videoEl.removeEventListener('loadedmetadata', handleLoaded);
      videoEl.removeEventListener('error', handleError, true);
    };
  }, [videoRef, videoUrl, seekTime]);
};
