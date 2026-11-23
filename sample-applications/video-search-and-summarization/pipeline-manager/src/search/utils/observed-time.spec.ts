// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { resolveObservedTime } from './observed-time';
import { SearchResult } from '../model/search.model';
import { VideoEntity } from 'src/video-upload/models/video.entity';

const hit = (metadata: Record<string, unknown>): SearchResult =>
  ({
    id: 'r',
    page_content: '',
    type: 'video',
    metadata,
  }) as unknown as SearchResult;

const video = (createdAt: string) => ({ createdAt }) as VideoEntity;

describe('resolveObservedTime', () => {
  it('uses upload time plus best-frame offset for uploaded videos', () => {
    expect(
      resolveObservedTime(
        hit({ best_frame_info: { timestamp: 2, is_live: false } }),
        video('2026-01-02T03:04:05.000Z'),
      ),
    ).toEqual({
      observedAt: '2026-01-02T03:04:07.000Z',
      timeSource: 'upload',
    });
  });

  it('falls back to seek_timestamp, then segment_start, for the offset', () => {
    const v = video('2026-01-02T00:00:00.000Z');
    expect(
      resolveObservedTime(hit({ seek_timestamp: 5, segment_start: 9 }), v)
        ?.observedAt,
    ).toBe('2026-01-02T00:00:05.000Z');
    expect(resolveObservedTime(hit({ segment_start: 9 }), v)?.observedAt).toBe(
      '2026-01-02T00:00:09.000Z',
    );
  });

  it('ignores the embedding created_at for uploaded videos', () => {
    expect(
      resolveObservedTime(
        hit({ created_at: '2030-01-01T00:00:00', best_frame_info: {} }),
      ),
    ).toBeUndefined();
  });

  it('uses the live segment epoch from media_path', () => {
    expect(
      resolveObservedTime(
        hit({
          best_frame_info: {
            is_live: true,
            timestamp: 1.5,
            media_path: 'live-streams/cam/segments/1790655530.mp4',
          },
        }),
      ),
    ).toEqual({
      observedAt: new Date(1790655531500).toISOString(),
      timeSource: 'live',
    });
  });

  it('falls back to the live segment created_at (naive = UTC)', () => {
    expect(
      resolveObservedTime(
        hit({
          best_frame_info: { is_live: true, timestamp: 1, media_path: 'x' },
          video_metadata: { created_at: '2026-05-06T07:08:09' },
        }),
      )?.observedAt,
    ).toBe('2026-05-06T07:08:10.000Z');
  });

  it('returns undefined when no time is known', () => {
    expect(
      resolveObservedTime(hit({ best_frame_info: { is_live: true } })),
    ).toBeUndefined();
    expect(resolveObservedTime(hit({}), video('not-a-date'))).toBeUndefined();
  });
});
