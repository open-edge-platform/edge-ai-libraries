// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { combineReducers, configureStore } from '@reduxjs/toolkit';
import { TypedUseSelectorHook, useDispatch, useSelector } from 'react-redux';

import notificationReducer from './notification/notificationSlice.ts';
import { SummaryReducers } from './summary/summarySlice.ts';
import { VideoChunkReducer } from './summary/videoChunkSlice.ts';
import { VideoFrameReducer } from './summary/videoFrameSlice.ts';
import { UIReducer } from './ui/ui.slice.ts';
import { VideoReducers } from './video/videoSlice.ts';
import { SearchReducers } from './search/searchSlice.ts';
import { StreamsReducers } from './streams/streamsSlice.ts';

/**
 * Slices that must never reach localStorage.
 *
 * `ui` is ephemeral view state. `streams` is live telemetry polled every few
 * seconds - persisting it would both write to disk continuously and show the
 * user yesterday's frame counts on the next page load.
 */
const NON_PERSISTED_SLICES = ['ui', 'streams'] as const;

export const loadFromLocalStorage = () => {
  try {
    const serialisedState = localStorage.getItem('reduxStore');
    if (serialisedState === null) return undefined;
    const state = JSON.parse(serialisedState);
    for (const slice of NON_PERSISTED_SLICES) {
      delete state[slice];
    }
    // The search query list is persisted so the sidebar renders instantly, but
    // it must be reconciled with the server on every fresh page load - otherwise
    // a browser refresh keeps showing queries that no longer exist server-side
    // (and re-running one 500s). `triggerLoad` is the one-shot "reload from the
    // server" signal SearchContainer watches; it is set false after the first
    // load, so force it back to true on rehydration to fetch exactly once per
    // page load. Steady-state watched-query updates arrive over the socket and
    // never go through this flag, so this does not add refresh flux.
    if (state.search && typeof state.search === 'object') {
      state.search.triggerLoad = true;
    }
    return state;
  } catch (err) {
    console.warn(err);
    return undefined;
  }
};

export const saveToLocalStorage = (state: ReturnType<typeof store.getState>) => {
  try {
    // Strip before serializing, not after reading back. Stripping only on load
    // still writes the excluded slices on every dispatch.
    const persistable = { ...state } as Record<string, unknown>;
    for (const slice of NON_PERSISTED_SLICES) {
      delete persistable[slice];
    }
    const serialState = JSON.stringify(persistable);
    localStorage.setItem('reduxStore', serialState);
  } catch (e) {
    console.warn(e);
  }
};

const store = configureStore({
  reducer: combineReducers({
    // conversations: conversationReducer,
    videoChunks: VideoChunkReducer,
    videoFrames: VideoFrameReducer,
    videos: VideoReducers,
    notifications: notificationReducer,
    summaries: SummaryReducers,
    search: SearchReducers,
    streams: StreamsReducers,
    ui: UIReducer,
  }),
  // `import.meta.env.PROD || true` was always true, leaving the DevTools
  // action log - which carries every dispatched payload - enabled in
  // production builds.
  devTools: !import.meta.env.PROD,
  preloadedState: loadFromLocalStorage(),
  middleware: (getDefaultMiddleware) => getDefaultMiddleware(),
});

store.subscribe(() => saveToLocalStorage(store.getState()));

export type AppDispatch = typeof store.dispatch;
export type RootState = ReturnType<typeof store.getState>;

export const useAppDispatch: () => AppDispatch = useDispatch;
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;

export default store;
