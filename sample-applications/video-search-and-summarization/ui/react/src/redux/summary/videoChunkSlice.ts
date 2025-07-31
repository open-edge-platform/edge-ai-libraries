// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { createSelector, createSlice, PayloadAction } from '@reduxjs/toolkit';
import { UIChunkForState, VideoChunkState } from './summary';
import { RootState } from '../store';

const initialState: VideoChunkState = {
  chunks: {},
  selectedSummary: null,
};

export const VideoChunkSlice = createSlice({
  name: 'chunks',
  initialState,
  reducers: {
    setSelectedSummary: (
      state: VideoChunkState,
      action: PayloadAction<string>,
    ) => {
      state.selectedSummary = action.payload;
    },
    addChunks: (
      state: VideoChunkState,
      action: PayloadAction<UIChunkForState[]>,
    ) => {
      const chunks = action.payload.reduce(
        (acc: Record<string, UIChunkForState>, curr: UIChunkForState) => {
          const chunkKey: string = [curr.stateId, curr.chunkId].join('#');

          acc[chunkKey] = curr;

          return acc;
        },
        {},
      );

      state.chunks = { ...state.chunks, ...chunks };
    },
  },
});

export const VideoChunksState = (root: RootState) => root.videoChunks;

export const VideoChunkActions = VideoChunkSlice.actions;
export const VideoChunkReducer = VideoChunkSlice.reducer;

export const VideoChunkSelector = createSelector(
  [VideoChunksState],
  (videoChunkState) => ({
    chunkKeys: videoChunkState.selectedSummary
      ? Object.values(videoChunkState.chunks)
          .filter((el) => el.stateId === videoChunkState.selectedSummary)
          .map((el) => [el.stateId, el.chunkId].join('#'))
      : [],

    chunkData: videoChunkState.chunks ?? null,
  }),
);
