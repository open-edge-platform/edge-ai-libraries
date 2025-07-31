// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { createSelector, createSlice, PayloadAction } from '@reduxjs/toolkit';
import { UIChunk, UIChunkForState, UIState, VideoChunkState } from './summary';
import { RootState } from '../store';
import { SummaryLoad } from './summarySlice';

const initialState: VideoChunkState = {
  chunks: {},
  selectedSummary: null,
};

export const VideoChunkSlice = createSlice({
  name: 'chunks',
  initialState,
  reducers: {
    setSelectedSummary: (state: VideoChunkState, action: PayloadAction<string>) => {
      state.selectedSummary = action.payload;
    },
    reset: (state: VideoChunkState) => {
      state.chunks = {};
    },
    addChunks: (state: VideoChunkState, action: PayloadAction<UIChunkForState[]>) => {
      const chunks = action.payload.reduce((acc: Record<string, UIChunkForState>, curr: UIChunkForState) => {
        const chunkKey: string = [curr.stateId, curr.chunkId].join('#');

        acc[chunkKey] = curr;

        return acc;
      }, {});

      state.chunks = { ...state.chunks, ...chunks };
    },
  },
  extraReducers: (builder) => {
    builder.addCase(SummaryLoad.pending, (state) => {
      state.chunks = {};
      state.selectedSummary = null;
    });
    builder.addCase(SummaryLoad.fulfilled, (state, action: PayloadAction<UIState[]>) => {
      let chunks: Record<string, UIChunkForState> = {};

      if (action.payload.length > 0) {
        state.selectedSummary = action.payload[0].stateId;
      }

      for (const state of action.payload) {
        const stateId = state.stateId;

        const stateChunks = state.chunks.reduce(
          (acc: Record<string, UIChunkForState>, curr: UIChunk) => {
            const chunkKey: string = [stateId, curr.chunkId].join('#');
            acc[chunkKey] = { ...curr, stateId };
            return acc;
          },
          {} as Record<string, UIChunkForState>,
        );

        chunks = { ...chunks, ...stateChunks };
      }

      state.chunks = chunks;
    });
  },
});

export const VideoChunksState = (root: RootState) => root.videoChunks;

export const VideoChunkActions = VideoChunkSlice.actions;
export const VideoChunkReducer = VideoChunkSlice.reducer;

export const VideoChunkSelector = createSelector([VideoChunksState], (videoChunkState) => ({
  chunkKeys: videoChunkState.selectedSummary
    ? Object.values(videoChunkState.chunks)
        .filter((el) => el.stateId === videoChunkState.selectedSummary)
        .map((el) => [el.stateId, el.chunkId].join('#'))
    : [],

  chunkData: videoChunkState.chunks ?? null,
}));
