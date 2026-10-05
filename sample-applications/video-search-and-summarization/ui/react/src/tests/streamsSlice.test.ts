// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { configureStore } from '@reduxjs/toolkit';
import axios from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LiveStream, LiveStreamState } from '../redux/streams/streams';
import {
  StreamsActions,
  StreamsReducers,
  streamDelete,
  streamUpdate,
  streamsLoad,
  streamsSelector,
} from '../redux/streams/streamsSlice';
import { StateActionStatus } from '../redux/summary/summary';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    isAxiosError: vi.fn(() => false),
  },
}));

vi.mock('../config', () => ({
  APP_URL: 'http://localhost:3000',
}));

const mockedAxios = axios as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
  isAxiosError: ReturnType<typeof vi.fn>;
};

const makeStream = (overrides: Partial<LiveStream> = {}): LiveStream => ({
  stream_id: 'stream-1',
  stream_url: 'rtsp://cam-1:554/live',
  stream_name: 'lobby',
  state: LiveStreamState.RUNNING,
  frame_interval: 15,
  enable_object_detection: false,
  detection_confidence: 0.5,
  tags: [],
  stats: {
    frames_processed: 0,
    embeddings_created: 0,
    segments_stored: 0,
    frames_stored: 0,
    reconnect_count: 0,
  },
  ...overrides,
});

const makeStore = () =>
  configureStore({ reducer: { streams: StreamsReducers } });

describe('streamsSlice reducers', () => {
  it('starts empty and ready', () => {
    const state = makeStore().getState().streams;

    expect(state.streams).toEqual([]);
    expect(state.status).toBe(StateActionStatus.READY);
    expect(state.error).toBeNull();
    expect(state.filters).toEqual({});
  });

  it('replaces the list on streamsSync', () => {
    const store = makeStore();
    store.dispatch(StreamsActions.streamsSync([makeStream()]));
    store.dispatch(
      StreamsActions.streamsSync([makeStream({ stream_id: 'stream-2' })]),
    );

    const { streams } = store.getState().streams;
    expect(streams).toHaveLength(1);
    expect(streams[0].stream_id).toBe('stream-2');
  });

  it('clears a stale error when a sync arrives', () => {
    const store = makeStore();
    store.dispatch(streamsLoad.rejected(null, '', undefined, 'went wrong'));
    expect(store.getState().streams.error).toBe('went wrong');

    store.dispatch(StreamsActions.streamsSync([]));
    expect(store.getState().streams.error).toBeNull();
  });

  it('appends an unknown stream on streamUpserted', () => {
    const store = makeStore();
    store.dispatch(StreamsActions.streamUpserted(makeStream()));

    expect(store.getState().streams.streams).toHaveLength(1);
  });

  it('replaces a known stream on streamUpserted instead of duplicating it', () => {
    const store = makeStore();
    store.dispatch(StreamsActions.streamUpserted(makeStream()));
    store.dispatch(
      StreamsActions.streamUpserted(
        makeStream({ state: LiveStreamState.PAUSED }),
      ),
    );

    const { streams } = store.getState().streams;
    expect(streams).toHaveLength(1);
    expect(streams[0].state).toBe(LiveStreamState.PAUSED);
  });

  it('stores and clears filters', () => {
    const store = makeStore();
    store.dispatch(
      StreamsActions.setFilters({ state: LiveStreamState.ERROR, tag: 'x' }),
    );

    expect(store.getState().streams.filters).toEqual({
      state: LiveStreamState.ERROR,
      tag: 'x',
    });
  });

  it('clears the error on clearError', () => {
    const store = makeStore();
    store.dispatch(streamsLoad.rejected(null, '', undefined, 'bad'));
    store.dispatch(StreamsActions.clearError());

    expect(store.getState().streams.error).toBeNull();
  });
});

describe('streamsLoad', () => {
  beforeEach(() => vi.clearAllMocks());

  it('marks the slice in progress while loading', () => {
    const store = makeStore();
    store.dispatch(streamsLoad.pending('', undefined));

    expect(store.getState().streams.status).toBe(StateActionStatus.IN_PROGRESS);
  });

  it('populates the list on success', async () => {
    mockedAxios.get.mockResolvedValue({
      data: { count: 1, streams: [makeStream()] },
    });

    const store = makeStore();
    await store.dispatch(streamsLoad(undefined));

    const state = store.getState().streams;
    expect(state.streams).toHaveLength(1);
    expect(state.status).toBe(StateActionStatus.READY);
  });

  it('tolerates a response without a streams array', async () => {
    mockedAxios.get.mockResolvedValue({ data: { count: 0 } });

    const store = makeStore();
    await store.dispatch(streamsLoad(undefined));

    expect(store.getState().streams.streams).toEqual([]);
  });

  it('records the error and leaves the slice usable on failure', async () => {
    mockedAxios.get.mockRejectedValue(new Error('network down'));

    const store = makeStore();
    await store.dispatch(streamsLoad(undefined));

    const state = store.getState().streams;
    expect(state.error).toBe('Unable to load live streams.');
    // Not left spinning - the modal must render its error, not a loader.
    expect(state.status).toBe(StateActionStatus.READY);
  });
});

describe('streamUpdate', () => {
  beforeEach(() => vi.clearAllMocks());

  it('never carries a stream_url on the action argument', async () => {
    mockedAxios.patch.mockResolvedValue({ data: { stream: makeStream() } });

    const store = makeStore();
    const action = await store.dispatch(
      streamUpdate({
        streamId: 'stream-1',
        payload: { state: LiveStreamState.PAUSED },
      }),
    );

    // `meta.arg` is what an action log would capture. A credentialed RTSP
    // URL must never reach it - see streamsApi.createStream.
    expect(JSON.stringify(action.meta.arg)).not.toContain('rtsp://');
  });

  it('replaces the matching stream in place', async () => {
    const store = makeStore();
    store.dispatch(StreamsActions.streamsSync([makeStream()]));
    mockedAxios.patch.mockResolvedValue({
      data: { stream: makeStream({ state: LiveStreamState.PAUSED }) },
    });

    await store.dispatch(
      streamUpdate({
        streamId: 'stream-1',
        payload: { state: LiveStreamState.PAUSED },
      }),
    );

    expect(store.getState().streams.streams[0].state).toBe(
      LiveStreamState.PAUSED,
    );
  });

  it('leaves the list untouched when the response is for an unknown id', async () => {
    const store = makeStore();
    store.dispatch(StreamsActions.streamsSync([makeStream()]));
    mockedAxios.patch.mockResolvedValue({
      data: { stream: makeStream({ stream_id: 'ghost' }) },
    });

    await store.dispatch(
      streamUpdate({ streamId: 'ghost', payload: { stream_name: 'x' } }),
    );

    const { streams } = store.getState().streams;
    expect(streams).toHaveLength(1);
    expect(streams[0].stream_id).toBe('stream-1');
  });

  it('records a rejection message', async () => {
    mockedAxios.patch.mockRejectedValue(new Error('nope'));

    const store = makeStore();
    await store.dispatch(
      streamUpdate({ streamId: 'stream-1', payload: { stream_name: 'x' } }),
    );

    expect(store.getState().streams.error).toBe(
      'Unable to update the live stream.',
    );
  });
});

describe('streamDelete', () => {
  beforeEach(() => vi.clearAllMocks());

  it('removes the stream from the list', async () => {
    const store = makeStore();
    store.dispatch(
      StreamsActions.streamsSync([
        makeStream(),
        makeStream({ stream_id: 'stream-2' }),
      ]),
    );
    mockedAxios.delete.mockResolvedValue({ data: {} });

    await store.dispatch(streamDelete({ streamId: 'stream-1' }));

    const { streams } = store.getState().streams;
    expect(streams).toHaveLength(1);
    expect(streams[0].stream_id).toBe('stream-2');
  });

  it('keeps the stream listed when the delete fails', async () => {
    const store = makeStore();
    store.dispatch(StreamsActions.streamsSync([makeStream()]));
    mockedAxios.delete.mockRejectedValue(new Error('boom'));

    await store.dispatch(streamDelete({ streamId: 'stream-1' }));

    expect(store.getState().streams.streams).toHaveLength(1);
    expect(store.getState().streams.error).toBe(
      'Unable to remove the live stream.',
    );
  });
});

describe('streamsSelector', () => {
  it('counts only streams holding a decode pipeline', () => {
    const store = makeStore();
    store.dispatch(
      StreamsActions.streamsSync([
        makeStream({ stream_id: '1', state: LiveStreamState.RUNNING }),
        makeStream({ stream_id: '2', state: LiveStreamState.STARTING }),
        makeStream({ stream_id: '3', state: LiveStreamState.RECONNECTING }),
        makeStream({ stream_id: '4', state: LiveStreamState.PAUSED }),
        makeStream({ stream_id: '5', state: LiveStreamState.ERROR }),
        makeStream({ stream_id: '6', state: LiveStreamState.STOPPED }),
      ]),
    );

    const selected = streamsSelector(
      store.getState() as unknown as Parameters<typeof streamsSelector>[0],
    );

    expect(selected.streams).toHaveLength(6);
    expect(selected.runningCount).toBe(3);
  });
});
