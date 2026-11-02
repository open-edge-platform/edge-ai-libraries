// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { configureStore } from '@reduxjs/toolkit';
import { render, screen } from '@testing-library/react';
import { Provider } from 'react-redux';
import { describe, expect, it, vi } from 'vitest';
import Navbar from '../components/Navbar/Navbar';
import notificationReducer from '../redux/notification/notificationSlice';
import { SearchReducers } from '../redux/search/searchSlice';
import { StreamsReducers } from '../redux/streams/streamsSlice';
import { SummaryReducers } from '../redux/summary/summarySlice';
import { VideoChunkReducer } from '../redux/summary/videoChunkSlice';
import { VideoFrameReducer } from '../redux/summary/videoFrameSlice';
import { UIReducer } from '../redux/ui/ui.slice';
import { VideoReducers } from '../redux/video/videoSlice';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../socket', () => ({
  socket: { emit: vi.fn(), on: vi.fn(), off: vi.fn(), connected: true },
}));

vi.mock('../redux/streams/streamsApi', () => ({
  streamsApi: {
    list: vi.fn(async () => ({ count: 0, streams: [] })),
    createStream: vi.fn(),
    updateStream: vi.fn(),
    deleteStream: vi.fn(),
    setState: vi.fn(),
  },
  streamErrorMessage: (_error: unknown, fallback: string) => fallback,
}));

// Hoisted so the `vi.mock` factory below - which vitest lifts above the
// imports - can close over it.
const flags = vi.hoisted(() => ({
  FEATURE_SEARCH: 'FEATURE_ON',
  FEATURE_SUMMARY: 'FEATURE_ON',
  FEATURE_CAMERA_CONFIG: 'FEATURE_OFF',
  FEATURE_LIVE_STREAMS: 'FEATURE_OFF',
}));

vi.mock('../config.ts', () => ({
  APP_URL: 'http://localhost:3000',
  ASSETS_ENDPOINT: '',
  SOCKET_APPEND: 'CONFIG_OFF',
  FEATURE_MUX: 'ATOMIC',
  NVR_API_BASE: 'http://nvr',
  get FEATURE_SEARCH() {
    return flags.FEATURE_SEARCH;
  },
  get FEATURE_SUMMARY() {
    return flags.FEATURE_SUMMARY;
  },
  get FEATURE_CAMERA_CONFIG() {
    return flags.FEATURE_CAMERA_CONFIG;
  },
  get FEATURE_LIVE_STREAMS() {
    return flags.FEATURE_LIVE_STREAMS;
  },
}));

const makeStore = () =>
  configureStore({
    reducer: {
      videoChunks: VideoChunkReducer,
      videoFrames: VideoFrameReducer,
      videos: VideoReducers,
      notifications: notificationReducer,
      summaries: SummaryReducers,
      search: SearchReducers,
      streams: StreamsReducers,
      ui: UIReducer,
    },
  });

const renderNavbar = () =>
  render(
    <Provider store={makeStore()}>
      <Navbar />
    </Provider>,
  );

describe('Navbar live-stream gating', () => {
  it('hides the live-streams button by default', () => {
    flags.FEATURE_LIVE_STREAMS = 'FEATURE_OFF';
    flags.FEATURE_SEARCH = 'FEATURE_ON';

    renderNavbar();

    expect(screen.queryByTestId('live-streams-button')).toBeNull();
  });

  it('shows the live-streams button when both search and the flag are on', () => {
    flags.FEATURE_LIVE_STREAMS = 'FEATURE_ON';
    flags.FEATURE_SEARCH = 'FEATURE_ON';

    renderNavbar();

    expect(screen.getByTestId('live-streams-button')).toBeTruthy();
  });

  it('hides the live-streams button when search is off', () => {
    // Live ingestion only writes to the search index, so the button is
    // meaningless without it.
    flags.FEATURE_LIVE_STREAMS = 'FEATURE_ON';
    flags.FEATURE_SEARCH = 'FEATURE_OFF';

    renderNavbar();

    expect(screen.queryByTestId('live-streams-button')).toBeNull();
  });

  it('keeps the camera-config button gated independently', () => {
    // Guard for the Metro AI Suite live-video-search deployment, which ships
    // this same image with CAMERA_CONFIG_FEATURE on and live streams off.
    flags.FEATURE_CAMERA_CONFIG = 'FEATURE_ON';
    flags.FEATURE_LIVE_STREAMS = 'FEATURE_OFF';
    flags.FEATURE_SEARCH = 'FEATURE_ON';

    renderNavbar();

    expect(screen.getByRole('button', { name: 'ConfigureCameras' })).toBeTruthy();
    expect(screen.queryByTestId('live-streams-button')).toBeNull();

    flags.FEATURE_CAMERA_CONFIG = 'FEATURE_OFF';
  });

  it('can show both buttons at once', () => {
    flags.FEATURE_CAMERA_CONFIG = 'FEATURE_ON';
    flags.FEATURE_LIVE_STREAMS = 'FEATURE_ON';
    flags.FEATURE_SEARCH = 'FEATURE_ON';

    renderNavbar();

    expect(screen.getByRole('button', { name: 'ConfigureCameras' })).toBeTruthy();
    expect(screen.getByTestId('live-streams-button')).toBeTruthy();

    flags.FEATURE_CAMERA_CONFIG = 'FEATURE_OFF';
    flags.FEATURE_LIVE_STREAMS = 'FEATURE_OFF';
  });
});
