// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FEATURE_SEARCH, FEATURE_MUX } from '../config';
import { FEATURE_STATE, FeatureMux } from './constant';

// Image search is available only in frame-embedding deployments (--search/--dual).
// The unified deployment (--unified) searches text summaries and is the only mode
// that uses the SUMMARY_SEARCH mux, so derive capability from existing flags
// rather than a dedicated one.
export const imageSearchEnabled: boolean =
  FEATURE_SEARCH === FEATURE_STATE.ON && FEATURE_MUX !== FeatureMux.SUMMARY_SEARCH;
