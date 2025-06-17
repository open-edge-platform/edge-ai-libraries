// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { createSelector, createSlice, PayloadAction } from '@reduxjs/toolkit';
import { ICDTO, SummaryState, SummaryStreamChunk, UIState, UIStatusForState, UISummaryState } from './summary';
import { RootState } from '../store';

const initialState: SummaryState = {
  summaries: {},
  selectedSummary: null,
};

export const SummarySlice = createSlice({
  name: 'summary',
  initialState,
  reducers: {
    addSummary: (state: SummaryState, action: PayloadAction<UIState>) => {
      const {
        stateId,
        userInputs,
        chunkingStatus,
        chunks,
        frames,
        summary,
        videoSummaryStatus,
        frameSummaries,
        frameSummaryStatus,
        systemConfig,
        inferenceConfig,
        videoId,
        title,
      } = action.payload;

      const summaryState: UISummaryState = {
        stateId,
        summary,
        userInputs,
        title,
        chunkingStatus,
        inferenceConfig,
        chunksCount: chunks.length,
        framesCount: frames.length,
        frameSummaries: frameSummaries.length,
        videoId,
        frameSummaryStatus,
        videoSummaryStatus,
        systemConfig,
      };

      state.summaries[stateId] = summaryState;

      // state.summaries[stateId] = { stateId, data: action.payload };
    },

    updateSummaryData: (state: SummaryState, action: PayloadAction<UIState>) => {
      const {
        stateId,

        chunkingStatus,
        chunks,
        frames,
        summary,
        userInputs,
        videoSummaryStatus,
        inferenceConfig,
        videoId,
        frameSummaries,
        frameSummaryStatus,
        systemConfig,
        title,
      } = action.payload;

      const summaryState: UISummaryState = {
        stateId,
        summary,
        userInputs,
        chunkingStatus,
        videoSummaryStatus,
        inferenceConfig,
        chunksCount: chunks.length,
        framesCount: frames.length,
        videoId,
        frameSummaries: frameSummaries.length,
        frameSummaryStatus,
        systemConfig,
        title,
      };

      state.summaries[stateId] = summaryState;
    },

    selectSummary: (state: SummaryState, action: PayloadAction<string>) => {
      state.selectedSummary = action.payload;
    },

    updateInferenceConfig: (state: SummaryState, action: PayloadAction<ICDTO>) => {
      const { stateId, ...iConfig } = action.payload;

      if (state.summaries[stateId]) {
        state.summaries[stateId].inferenceConfig = iConfig;
      }
    },

    updateSummaryStatus: (state: SummaryState, action: PayloadAction<UIStatusForState>) => {
      const { stateId, ...statuses } = action.payload;

      if (state.summaries[stateId]) {
        state.summaries[stateId] = { ...state.summaries[stateId], ...statuses };
      }
    },

    updateSummaryChunk: (state: SummaryState, action: PayloadAction<SummaryStreamChunk>) => {
      const { stateId, streamChunk } = action.payload;

      if (state.summaries[stateId]) {
        state.summaries[stateId].summary = streamChunk;
      }
    },

    deleteSummary: (state: SummaryState, action: PayloadAction<string>) => {
      const stateId = action.payload;

      if (state.summaries[stateId]) {
        delete state.summaries[stateId];
      }

      if (state.selectedSummary == stateId) {
        const summaries = Object.keys(state.summaries);
        if (summaries.length > 0) {
          state.selectedSummary = summaries[0];
        } else {
          state.selectedSummary = null;
        }
      }
    },
  },
});

const selectSummaryState = (state: RootState) => state.summaries;

export const SummarySelector = createSelector([selectSummaryState], (summaryState) => ({
  summaries: summaryState.summaries ?? [],

  getSystemConfig: summaryState.selectedSummary
    ? summaryState.summaries[summaryState.selectedSummary].systemConfig
    : null,

  getChunkCount: summaryState.selectedSummary ? summaryState.summaries[summaryState.selectedSummary!].chunksCount : 0,
  getFrameCount: summaryState.selectedSummary ? summaryState.summaries[summaryState.selectedSummary].framesCount : 0,

  selectedSummaryId: summaryState.selectedSummary,
  selectedSummary: summaryState.selectedSummary ? summaryState.summaries[summaryState.selectedSummary] : null,
  sidebarSummaries: Object.values(summaryState.summaries).map((summary) => ({
    selected: summaryState.selectedSummary == summary.stateId,
    ...summary,
  })),
  summaryIds: Object.keys(summaryState.summaries),
}));

export const SummaryActions = SummarySlice.actions;
export const SummaryReducers = SummarySlice.reducer;
