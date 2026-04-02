// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { getSafePreviewVideoUrl } from '../utils/util';

describe('getSafePreviewVideoUrl', () => {
  it('allows locally created blob preview URLs', () => {
    expect(getSafePreviewVideoUrl('blob:http://localhost/mock-preview', 'http://localhost/assets')).toBe(
      'blob:http://localhost/mock-preview'
    );
  });

  it('allows preview URLs that stay under the configured assets endpoint', () => {
    expect(
      getSafePreviewVideoUrl('http://localhost/assets/demo-bucket/video.mp4', 'http://localhost/assets')
    ).toBe('http://localhost/assets/demo-bucket/video.mp4');
  });

  it('rejects preview URLs outside the configured assets endpoint', () => {
    expect(
      getSafePreviewVideoUrl('http://localhost/other-assets/demo-bucket/video.mp4', 'http://localhost/assets')
    ).toBeNull();
  });
});
