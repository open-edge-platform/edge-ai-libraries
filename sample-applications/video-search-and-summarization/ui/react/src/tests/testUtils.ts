// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { configureStore } from '@reduxjs/toolkit';
import { SearchQueryStatus, SearchQueryUI, SearchResult, SearchState } from '../redux/search/search';
import { SearchResultTagFields } from '../redux/search/searchResult';
import { RootState } from '../redux/store';
import notificationReducer from '../redux/notification/notificationSlice';
import { SummaryReducers } from '../redux/summary/summarySlice';
import { VideoChunkReducer } from '../redux/summary/videoChunkSlice';
import { VideoFrameReducer } from '../redux/summary/videoFrameSlice';
import { UIReducer } from '../redux/ui/ui.slice';
import { VideoReducers } from '../redux/video/videoSlice';
import { SearchReducers } from '../redux/search/searchSlice';
import { StreamsReducers } from '../redux/streams/streamsSlice';
import { GeoReducer } from '../redux/geo/geoSlice';
import { UISliceState } from '../redux/ui/ui.model';
import { initialState as uiInitialState } from '../redux/ui/ui.slice';
import { Video } from '../redux/video/video';

// Mirrors the reducer map in redux/store.ts, which does not export it.
const testRootReducer = {
  videoChunks: VideoChunkReducer,
  videoFrames: VideoFrameReducer,
  videos: VideoReducers,
  notifications: notificationReducer,
  summaries: SummaryReducers,
  search: SearchReducers,
  streams: StreamsReducers,
  ui: UIReducer,
  geo: GeoReducer,
};

type SearchResultMetadata = SearchResult['metadata'];

const TEST_TIMESTAMP = '2026-01-01T00:00:00Z';

export type TestStateOverrides = {
  [Slice in keyof RootState]?: Partial<RootState[Slice]>;
};

export interface SearchResultOverrides extends Omit<Partial<SearchResult>, 'metadata' | 'video'> {
  metadata?: Partial<Omit<SearchResultMetadata, 'tags'>> & SearchResultTagFields;
  video?: Partial<Video> | null;
}

export interface SearchQueryOverrides extends Omit<Partial<SearchQueryUI>, 'results'> {
  results?: SearchResult[];
}

export const createUiState = (overrides: Partial<UISliceState> = {}): UISliceState => ({
  ...uiInitialState,
  ...overrides,
});

export const createSearchResult = (overrides: SearchResultOverrides = {}): SearchResult => {
  const { metadata, video, ...resultOverrides } = overrides;
  const baseVideo: Video = {
    videoId: 'video-1',
    name: 'Test Video',
    url: 'video-1/source.mp4',
    tags: [],
    createdAt: TEST_TIMESTAMP,
    updatedAt: TEST_TIMESTAMP,
    dataStore: {
      bucket: 'test-bucket',
      objectName: 'video-1',
      fileName: 'source.mp4',
    },
  };
  const baseMetadata: SearchResultMetadata = {
    bucket_name: 'test-bucket',
    clip_duration: 10,
    tags: 'test',
    date: '2026-01-01',
    date_time: TEST_TIMESTAMP,
    day: 1,
    fps: 30,
    frames_in_clip: 300,
    hours: 0,
    id: 'video-1',
    interval_num: 1,
    minutes: 0,
    month: 1,
    seconds: 0,
    time: '00:00:00',
    timestamp: 0,
    total_frames: 300,
    video: 'source.mp4',
    video_id: 'video-1',
    video_path: '/videos/video-1/source.mp4',
    video_rel_url: '/test-bucket/video-1/source.mp4',
    video_remote_path: 'video-1/source.mp4',
    video_url: '',
    year: 2026,
    relevance_score: 0.9,
  };

  return {
    id: 'result-1',
    page_content: 'Test search result',
    type: 'video',
    ...resultOverrides,
    metadata: { ...baseMetadata, ...metadata } as SearchResultMetadata,
    // The API can return a null video at runtime even though the SearchResult type does not allow it.
    video: (video === null ? null : { ...baseVideo, ...video }) as Video,
  };
};

export const createSearchQuery = (overrides: SearchQueryOverrides = {}): SearchQueryUI => ({
  queryId: 'query-1',
  query: 'test query',
  watch: false,
  results: [],
  queryStatus: SearchQueryStatus.IDLE,
  tags: [],
  topK: 4,
  createdAt: TEST_TIMESTAMP,
  updatedAt: TEST_TIMESTAMP,
  ...overrides,
});

export const createSearchState = (overrides: Partial<SearchState> = {}): SearchState => ({
  searchQueries: [],
  suggestedTags: [],
  unreads: [],
  selectedQuery: null,
  triggerLoad: false,
  ...overrides,
});

export const createTestState = (overrides: TestStateOverrides = {}): RootState => {
  const state = createTestStore().getState();
  const mergedState = { ...state };

  const mergeSlice = <Slice extends keyof RootState>(slice: Slice): void => {
    mergedState[slice] = Object.assign({}, state[slice], overrides[slice]) as RootState[Slice];
  };
  (Object.keys(overrides) as (keyof RootState)[]).forEach(mergeSlice);

  return mergedState;
};

export const createTestStore = (overrides?: TestStateOverrides) =>
  configureStore({
    reducer: testRootReducer,
    preloadedState: overrides ? createTestState(overrides) : undefined,
  });

export type TestStore = ReturnType<typeof createTestStore>;
