// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  createAsyncThunk,
  createSelector,
  createSlice,
  PayloadAction,
} from '@reduxjs/toolkit';
import { RootState } from '../store';
import { StateActionStatus } from '../summary/summary';
import {
  LiveStream,
  LiveStreamFilters,
  LiveStreamListRO,
  LiveStreamPurgeOptions,
  LiveStreamState,
  LiveStreamUpdatePayload,
  StreamsState,
} from './streams';
import { streamErrorMessage, streamsApi } from './streamsApi';

const initialState: StreamsState = {
  streams: [],
  status: StateActionStatus.READY,
  error: null,
  filters: {},
};

export const streamsLoad = createAsyncThunk<
  LiveStreamListRO,
  LiveStreamFilters | undefined,
  { rejectValue: string }
>('streams/load', async (filters, { rejectWithValue }) => {
  try {
    return await streamsApi.list(filters ?? {});
  } catch (error) {
    return rejectWithValue(
      streamErrorMessage(error, 'Unable to load live streams.'),
    );
  }
});

/**
 * Update a stream's configuration, or pause/resume it.
 *
 * Safe as a thunk: `LiveStreamUpdatePayload` has no `stream_url` member, so
 * no credential can reach `meta.arg`. Creation is handled outside Redux for
 * exactly that reason - see `streamsApi`.
 */
export const streamUpdate = createAsyncThunk<
  LiveStream,
  { streamId: string; payload: LiveStreamUpdatePayload },
  { rejectValue: string }
>('streams/update', async ({ streamId, payload }, { rejectWithValue }) => {
  try {
    return await streamsApi.updateStream(streamId, payload);
  } catch (error) {
    return rejectWithValue(
      streamErrorMessage(error, 'Unable to update the live stream.'),
    );
  }
});

export const streamDelete = createAsyncThunk<
  string,
  { streamId: string; purge?: LiveStreamPurgeOptions },
  { rejectValue: string }
>('streams/delete', async ({ streamId, purge }, { rejectWithValue }) => {
  try {
    await streamsApi.deleteStream(streamId, purge ?? {});
    return streamId;
  } catch (error) {
    return rejectWithValue(
      streamErrorMessage(error, 'Unable to remove the live stream.'),
    );
  }
});

export const StreamsSlice = createSlice({
  name: 'streams',
  initialState,
  reducers: {
    /** Applied from the `streams:sync` socket event. */
    streamsSync: (state, action: PayloadAction<LiveStream[]>) => {
      state.streams = action.payload;
      state.status = StateActionStatus.READY;
      state.error = null;
    },
    /** Merge one stream in after a direct (non-thunk) create. */
    streamUpserted: (state, action: PayloadAction<LiveStream>) => {
      const index = state.streams.findIndex(
        (stream) => stream.stream_id === action.payload.stream_id,
      );
      if (index === -1) {
        state.streams.push(action.payload);
      } else {
        state.streams[index] = action.payload;
      }
    },
    setFilters: (state, action: PayloadAction<LiveStreamFilters>) => {
      state.filters = action.payload;
    },
    clearError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(streamsLoad.pending, (state) => {
        state.status = StateActionStatus.IN_PROGRESS;
      })
      .addCase(streamsLoad.fulfilled, (state, action) => {
        state.status = StateActionStatus.READY;
        state.streams = action.payload.streams ?? [];
        state.error = null;
      })
      .addCase(streamsLoad.rejected, (state, action) => {
        state.status = StateActionStatus.READY;
        state.error = action.payload ?? 'Unable to load live streams.';
      })
      .addCase(streamUpdate.fulfilled, (state, action) => {
        const index = state.streams.findIndex(
          (stream) => stream.stream_id === action.payload.stream_id,
        );
        if (index !== -1) state.streams[index] = action.payload;
        state.error = null;
      })
      .addCase(streamUpdate.rejected, (state, action) => {
        state.error = action.payload ?? 'Unable to update the live stream.';
      })
      .addCase(streamDelete.fulfilled, (state, action) => {
        state.streams = state.streams.filter(
          (stream) => stream.stream_id !== action.payload,
        );
        state.error = null;
      })
      .addCase(streamDelete.rejected, (state, action) => {
        state.error = action.payload ?? 'Unable to remove the live stream.';
      });
  },
});

const selectStreamsState = (state: RootState) => state.streams;

export const streamsSelector = createSelector(
  [selectStreamsState],
  (streamsState) => ({
    streams: streamsState.streams,
    status: streamsState.status,
    error: streamsState.error,
    filters: streamsState.filters,
    /** Only streams actively consuming a decode pipeline. */
    runningCount: streamsState.streams.filter((stream) =>
      [
        LiveStreamState.RUNNING,
        LiveStreamState.STARTING,
        LiveStreamState.RECONNECTING,
      ].includes(stream.state),
    ).length,
  }),
);

export const StreamsActions = StreamsSlice.actions;
export const StreamsReducers = StreamsSlice.reducer;
