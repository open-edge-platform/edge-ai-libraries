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

  it('allows http preview URLs that stay under the configured assets endpoint', () => {
    expect(
      getSafePreviewVideoUrl('http://localhost/assets/demo-bucket/video.mp4', 'http://localhost/assets')
    ).toBe('http://localhost/assets/demo-bucket/video.mp4');
  });

  it('allows https preview URLs that stay under the configured assets endpoint', () => {
    expect(
      getSafePreviewVideoUrl('https://localhost/assets/demo-bucket/video.mp4', 'https://localhost/assets')
    ).toBe('https://localhost/assets/demo-bucket/video.mp4');
  });

  it('rejects preview URLs outside the configured assets endpoint', () => {
    expect(
      getSafePreviewVideoUrl('http://localhost/other-assets/demo-bucket/video.mp4', 'http://localhost/assets')
    ).toBeNull();
  });

  it('rejects javascript URLs', () => {
    expect(getSafePreviewVideoUrl('javascript:alert(1)//demo-bucket/video.mp4', 'javascript:alert(1)')).toBeNull();
  });

  it('rejects data URLs', () => {
    expect(getSafePreviewVideoUrl('data:text/html,/demo-bucket/video.mp4', 'data:text/html,')).toBeNull();
  });

  it('rejects invalid URL strings', () => {
    expect(getSafePreviewVideoUrl('not-a-url', 'http://localhost/assets')).toBeNull();
  });
});
