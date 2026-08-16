// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest';

import { resolveSearchResultVideoUrl, resolveVideoUrl } from '../redux/video/videoUrl';

const ASSETS = '/datastore';

describe('resolveVideoUrl', () => {
  it('builds an object-store path from the video entity', () => {
    const video = { url: 'vid-1/source.mp4', dataStore: { bucket: 'video-summary' } } as any;
    expect(resolveVideoUrl(video, ASSETS)).toBe('/datastore/video-summary/vid-1/source.mp4');
  });

  it('returns null without a video', () => {
    expect(resolveVideoUrl(null, ASSETS)).toBeNull();
  });
});

describe('resolveSearchResultVideoUrl', () => {
  it('derives a direct object-store URL from bucket_name and video_id', () => {
    expect(
      resolveSearchResultVideoUrl({ bucket_name: 'video-summary', video_id: 'vid-1' }, ASSETS),
    ).toBe('/datastore/video-summary/vid-1/source.mp4');
  });

  it('never falls back to the dataprep download API', () => {
    const url = resolveSearchResultVideoUrl(
      {
        bucket_name: 'video-summary',
        video_id: 'vid-1',
        video_url: 'http://multimodal-dataprep:8000/v1/dataprep/media/download?video_id=vid-1',
        video_rel_url: '/v1/dataprep/media/download?video_id=vid-1',
      },
      ASSETS,
    );

    expect(url).toBe('/datastore/video-summary/vid-1/source.mp4');
    expect(url).not.toContain('dataprep');
    expect(url).not.toContain('multimodal-dataprep:8000');
  });

  it('prefers a metadata URL that is already an object-store path', () => {
    expect(
      resolveSearchResultVideoUrl(
        {
          bucket_name: 'video-summary',
          video_id: 'vid-1',
          video_rel_url: '/datastore/video-summary/vid-1/01.54.mp4',
        },
        ASSETS,
      ),
    ).toBe('/datastore/video-summary/vid-1/01.54.mp4');
  });

  it('rejects unsafe bucket or video id values', () => {
    expect(
      resolveSearchResultVideoUrl({ bucket_name: '../etc', video_id: 'vid-1' }, ASSETS),
    ).toBeNull();
    expect(
      resolveSearchResultVideoUrl({ bucket_name: 'video-summary', video_id: '../../x' }, ASSETS),
    ).toBeNull();
  });

  it('returns null when metadata is missing', () => {
    expect(resolveSearchResultVideoUrl(undefined, ASSETS)).toBeNull();
    expect(resolveSearchResultVideoUrl({}, ASSETS)).toBeNull();
  });
});
