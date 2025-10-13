// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { createAsyncThunk, createSelector, createSlice, PayloadAction } from '@reduxjs/toolkit';
import { VideosRO, VideosState } from './video';
import { RootState } from '../store';
import axios from 'axios';
import { APP_URL, ASSETS_ENDPOINT } from '../../config';
import { StateActionStatus } from '../summary/summary';

const initialState: VideosState = {
  videos: [],
  status: StateActionStatus.READY,
};

export const VideoSlice = createSlice({
  name: 'videos',
  initialState,
  reducers: {
    addVideo: (state: VideosState, action) => {
      state.videos.push(action.payload);
    },
    removeVideo: (state: VideosState, action) => {
      state.videos = state.videos.filter((video) => video.videoId !== action.payload.videoId);
    },
    updateVideo: (state: VideosState, action) => {
      const index = state.videos.findIndex((video) => video.videoId === action.payload.videoId);
      if (index !== -1) {
        state.videos[index] = { ...state.videos[index], ...action.payload };
      }
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(videosLoad.pending, (state) => {
        state.status = StateActionStatus.IN_PROGRESS;
      })
      .addCase(videosLoad.fulfilled, (state, action: PayloadAction<VideosRO>) => {
        state.status = StateActionStatus.READY;
        state.videos = action.payload.videos;
      })
      .addCase(videosLoad.rejected, (state) => {
        state.status = StateActionStatus.READY;
      });
  },
});

export const videosLoad = createAsyncThunk('videos/load', async () => {
  const videosRes = await axios.get<VideosRO>(`${APP_URL}/videos`);
  return videosRes.data;
});

const selectVideoState = (state: RootState) => state.videos;

export const videosSelector = createSelector([selectVideoState], (videosState) => ({
  getVideo: (videoId: string) => {
    return videosState.videos.find((video) => video.videoId === videoId);
  },
  getVideoUrl: (videoId: string) => {
    const video = videosState.videos.find((video) => video.videoId === videoId);

    console.log(video);

    if (video?.dataStore) {
      return `${ASSETS_ENDPOINT}/${video.dataStore.bucket}/${video.url}`;
    }

    return null;
  },
}));

export const VideoActions = VideoSlice.actions;
export const VideoReducers = VideoSlice.reducer;
