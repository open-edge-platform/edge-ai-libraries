// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Video } from './video';

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
