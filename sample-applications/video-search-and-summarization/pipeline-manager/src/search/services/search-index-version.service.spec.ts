// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { SearchIndexVersionService } from './search-index-version.service';

describe('SearchIndexVersionService', () => {
  let service: SearchIndexVersionService;

  beforeEach(() => {
    service = new SearchIndexVersionService();
  });

  it('should start clean', () => {
    expect(service.isDirty()).toBe(false);
    expect(service.getIndexVersion()).toBe(0);
    expect(service.getLastEmbeddingAt()).toBeNull();
  });

  it('should become dirty when embeddings are added', () => {
    service.markDirty();

    expect(service.isDirty()).toBe(true);
    expect(service.getIndexVersion()).toBe(1);
    expect(service.getLastEmbeddingAt()).not.toBeNull();
  });

  it('should be clean again once the current version is refreshed', () => {
    service.markDirty();
    service.markRefreshed(service.getIndexVersion());

    expect(service.isDirty()).toBe(false);
  });

  it('should stay dirty for embeddings that land mid-cycle', () => {
    service.markDirty();
    const versionAtStart = service.getIndexVersion();

    service.markDirty();
    service.markRefreshed(versionAtStart);

    expect(service.isDirty()).toBe(true);
  });

  it('should report quiet only after the quiet period has elapsed', () => {
    const now = 1_000_000;
    jest.spyOn(Date, 'now').mockReturnValue(now);
    service.markDirty();

    expect(service.isQuiet(2000, now + 500)).toBe(false);
    expect(service.isQuiet(2000, now + 2000)).toBe(true);
    expect(service.isQuiet(0, now)).toBe(true);

    jest.restoreAllMocks();
  });
});
