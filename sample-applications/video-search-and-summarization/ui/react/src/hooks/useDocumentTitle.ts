// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { useEffect } from 'react';
import { useAppSelector } from '../redux/store';
import { uiSelector } from '../redux/ui/ui.slice';
import { FEATURE_SEARCH, FEATURE_SUMMARY } from '../config';
import { FEATURE_STATE } from '../utils/constant';

export const useDocumentTitle = () => {
  const { selectedMux } = useAppSelector(uiSelector);

  useEffect(() => {
    const hasSearch = FEATURE_SEARCH === FEATURE_STATE.ON;
    const hasSummary = FEATURE_SUMMARY === FEATURE_STATE.ON;
    
    let title = 'Intel EGAI Video';
    
    // If both features are enabled (--all mode)
    if (hasSearch && hasSummary) {
      title = 'Intel EGAI Video Search-Summarization';
    }
    // If only search is enabled
    else if (hasSearch) {
      title = 'Intel EGAI Video Search';
    }
    // If only summary is enabled
    else if (hasSummary) {
      title = 'Intel EGAI Video Summarization';
    }

    document.title = title;
  }, [selectedMux]);
};