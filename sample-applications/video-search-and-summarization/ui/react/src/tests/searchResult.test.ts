// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from 'vitest';
import { getSearchResultTags, getSearchResultVideoId } from '../redux/search/searchResult';
import { createSearchResult } from './testUtils';

describe('search result presentation helpers', () => {
  it('normalizes CSV, array, object, nested metadata, and video tags once', () => {
    const result = createSearchResult({
      metadata: {
        tags: [' lobby ', { name: 'dock' }, { label: 'gate' }, { tag: 'lobby' }],
        video_metadata: { tags: ['parking'] },
      },
      video: { tags: ['dock', 'office'] },
    });

    expect(getSearchResultTags(result)).toEqual(['lobby', 'dock', 'gate', 'parking', 'office']);
  });

  it('uses metadata id and then the enriched video id when video_id is absent', () => {
    const metadataFallback = createSearchResult({ metadata: { video_id: '', id: 'metadata-id' } });
    const videoFallback = createSearchResult({
      metadata: { video_id: '', id: '' },
      video: { videoId: 'enriched-id' },
    });

    expect(getSearchResultVideoId(metadataFallback)).toBe('metadata-id');
    expect(getSearchResultVideoId(videoFallback)).toBe('enriched-id');
  });
});
