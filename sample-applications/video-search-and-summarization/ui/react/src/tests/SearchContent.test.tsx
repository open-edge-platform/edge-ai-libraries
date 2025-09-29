// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';

import SearchContent from '../components/Search/SearchContent.tsx';
import i18n from '../utils/i18n';
import { SearchReducers } from '../redux/search/searchSlice.ts';
import { VideoReducers } from '../redux/video/videoSlice.ts';
import { StateActionStatus } from '../redux/summary/summary.ts';
import { SearchQueryUI, SearchResult } from '../redux/search/search.ts';

// Mock i18next
vi.mock('react-i18next', async () => ({
  ...await vi.importActual('react-i18next'),
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

// Mock VideoTile component
vi.mock('../../redux/search/VideoTile.tsx', () => ({
  VideoTile: ({ videoId, relevance, startTime }: any) => (
    <div 
      className="video-tile"
    >
      <video controls>
        <source src="" />
      </video>
      <div className="relevance">
        Relevance Score: {relevance !== null && relevance !== undefined ? relevance.toFixed(3) : 'N/A'}
      </div>
    </div>
  ),
}));

// Helper function to create mock SearchResult
const createMockSearchResult = (id: string, videoId: string, relevanceScore: number, timestamp: number): SearchResult => ({
  id: id,
  metadata: {
    bucket_name: 'test-bucket',
    clip_duration: 30,
    date: '2024-01-01',
    date_time: '2024-01-01 10:00:00',
    day: 1,
    fps: 30,
    frames_in_clip: 900,
    hours: 10,
    id: id,
    interval_num: 1,
    minutes: 0,
    month: 1,
    seconds: 0,
    time: '10:00:00',
    timestamp: timestamp,
    total_frames: 1000,
    video: 'test-video.mp4',
    video_id: videoId,
    video_path: `/videos/${videoId}.mp4`,
    video_rel_url: `/videos/${videoId}.mp4`,
    video_remote_path: `/remote/videos/${videoId}.mp4`,
    video_url: `http://localhost/videos/${videoId}.mp4`,
    year: 2024,
    relevance_score: relevanceScore,
  },
  page_content: 'Test page content',
  type: 'video'
});

// Helper function to create mock SearchQueryUI
const createMockQuery = (queryId: string, query: string, topK: number = 4, results: SearchResult[] = []): SearchQueryUI => ({
  queryId,
  query,
  topK,
  dbId: 1,
  watch: false,
  results,
  tags: [],
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-01T00:00:00Z'
});

const createMockStore = (initialState: any = {}) => {
  return configureStore({
    reducer: {
      search: SearchReducers,
      videos: VideoReducers,
    },
    preloadedState: {
      search: {
        searchQueries: [],
        selectedQuery: null,
        unreads: [],
        triggerLoad: false,
        topK: 4,
        ...initialState,
      },
      videos: {
        videos: [],
        status: StateActionStatus.READY,
      },
    },
  });
};

describe('SearchContent Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderSearchContent = (storeState: any = {}) => {
    const store = createMockStore(storeState);
    return { 
      store,
      ...render(
        <Provider store={store}>
          <I18nextProvider i18n={i18n}>
            <SearchContent />
          </I18nextProvider>
        </Provider>,
      )
    };
  };

  describe('Basic Rendering', () => {
    it('should render no query selected message when no query is selected', () => {
      renderSearchContent();
      
      expect(screen.getByText('searchNothingSelected')).toBeInTheDocument();
    });

    it('should render query header when query is selected', () => {
      const mockQuery: SearchQueryUI = {
        queryId: 'query-1',
        query: 'Test Query 1',
        topK: 4,
        dbId: 1,
        watch: false,
        results: [],
        tags: [],
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:00Z'
      };

      renderSearchContent({
        selectedQuery: 'query-1', // This should be the ID, not the object
        searchQueries: [mockQuery],
      });
      
      expect(screen.getAllByText('Test Query 1')[0]).toBeInTheDocument();
      expect(screen.getByText('topK')).toBeInTheDocument();
    });

    it('should render videos container when query is selected', () => {
      const mockResults: SearchResult[] = [
        createMockSearchResult('result-1', 'video-1', 0.95, 120),
        createMockSearchResult('result-2', 'video-2', 0.87, 180)
      ];

      const mockQuery = createMockQuery('query-1', 'Test Query 1', 4, mockResults);

      renderSearchContent({
        selectedQuery: 'query-1', // Query ID
        searchQueries: [mockQuery],
      });
      
      expect(document.querySelectorAll("video")).toHaveLength(2);
    });
  });

  describe('Query Header', () => {
    it('should display query title in tooltip', () => {
      const mockQuery = createMockQuery(
        'query-1',
        'This is a very long query title that should be displayed in tooltip',
        4
      );

      renderSearchContent({
        selectedQuery: 'query-1',
        searchQueries: [mockQuery],
      });
      
      expect(screen.getAllByText('This is a very long query title that should be displayed in tooltip')[0]).toBeInTheDocument();
    });

    it('should render topK slider with correct value', () => {
      const mockQuery = createMockQuery('query-1', 'Test Query 1', 8);

      renderSearchContent({
        selectedQuery: 'query-1',
        searchQueries: [mockQuery],
      });
      
      expect(screen.getByText('topK')).toBeInTheDocument();
      const slider = screen.getByRole('slider');
      expect(slider).toHaveValue(8);
    });

    it('should update topK when slider value changes', () => {
      const mockQuery = createMockQuery('query-1', 'Test Query 1', 5);

      const { store } = renderSearchContent({
        selectedQuery: 'query-1',
        searchQueries: [mockQuery],
      });
      
      const input = screen.getByRole('spinbutton');
      fireEvent.change(input, { target: { value: '10' } });
      
      const state = store.getState();
      expect(state.search.searchQueries[0].topK).toBe(10);
    });

    it('should render slider with correct min, max, and step values', () => {
      const mockQuery = createMockQuery('query-1', 'Test Query 1', 4);

      renderSearchContent({
        selectedQuery: 'query-1',
        searchQueries: [mockQuery],
      });
      
      const input = screen.getByRole('spinbutton');
      expect(input).toHaveAttribute('min', '1');
      expect(input).toHaveAttribute('max', '20');
      expect(input).toHaveAttribute('step', '1');
    });
  });







  describe('Edge Cases', () => {
    it('should handle undefined selected query', () => {
      renderSearchContent({
        selectedQuery: null,
        searchQueries: [],
      });
      
      expect(screen.getByText('searchNothingSelected')).toBeInTheDocument();
    });
  });
});
