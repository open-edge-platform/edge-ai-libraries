//Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { renderHook } from '@testing-library/react';
import { vi, describe, it, beforeEach, afterEach, expect } from 'vitest';
import * as redux from '../redux/store';
import * as config from '../config';
import * as constant from '../utils/constant';
import { useDocumentTitle } from '../hooks/useDocumentTitle';

describe('useDocumentTitle', () => {
  let originalTitle: string;
  let useAppSelectorSpy: ReturnType<typeof vi.spyOn>;
  let featureSearchSpy: ReturnType<typeof vi.spyOn>;
  let featureSummarySpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    originalTitle = document.title;
    useAppSelectorSpy = vi.spyOn(redux, 'useAppSelector').mockReturnValue({ selectedMux: null });
  });

  afterEach(() => {
    document.title = originalTitle;
    useAppSelectorSpy.mockRestore();
    featureSearchSpy?.mockRestore();
    featureSummarySpy?.mockRestore();
  });

  it('sets title for both features ON', () => {
    featureSearchSpy = vi.spyOn(config, 'FEATURE_SEARCH', 'get').mockReturnValue(constant.FEATURE_STATE.ON);
    featureSummarySpy = vi.spyOn(config, 'FEATURE_SUMMARY', 'get').mockReturnValue(constant.FEATURE_STATE.ON);
    renderHook(() => useDocumentTitle());
    expect(document.title).toBe('Intel EGAI Video Search-Summarization');
  });

  it('sets title for only search ON', () => {
    featureSearchSpy = vi.spyOn(config, 'FEATURE_SEARCH', 'get').mockReturnValue(constant.FEATURE_STATE.ON);
    featureSummarySpy = vi.spyOn(config, 'FEATURE_SUMMARY', 'get').mockReturnValue(constant.FEATURE_STATE.OFF);
    renderHook(() => useDocumentTitle());
    expect(document.title).toBe('Intel EGAI Video Search');
  });

  it('sets title for only summary ON', () => {
    featureSearchSpy = vi.spyOn(config, 'FEATURE_SEARCH', 'get').mockReturnValue(constant.FEATURE_STATE.OFF);
    featureSummarySpy = vi.spyOn(config, 'FEATURE_SUMMARY', 'get').mockReturnValue(constant.FEATURE_STATE.ON);
    renderHook(() => useDocumentTitle());
    expect(document.title).toBe('Intel EGAI Video Summarization');
  });

  it('sets default title if both OFF', () => {
    featureSearchSpy = vi.spyOn(config, 'FEATURE_SEARCH', 'get').mockReturnValue(constant.FEATURE_STATE.OFF);
    featureSummarySpy = vi.spyOn(config, 'FEATURE_SUMMARY', 'get').mockReturnValue(constant.FEATURE_STATE.OFF);
    renderHook(() => useDocumentTitle());
    expect(document.title).toBe('Intel EGAI Video');
  });
});
