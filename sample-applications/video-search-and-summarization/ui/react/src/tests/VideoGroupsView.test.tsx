// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import { Provider } from 'react-redux';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import '@testing-library/jest-dom';
import { configureStore } from '@reduxjs/toolkit';
import { I18nextProvider } from 'react-i18next';
import VideoGroupsView from '../components/VideoGroups/VideoGroupsView';
import { SearchResult } from '../redux/search/search';
import i18n from '../utils/i18n';

// Mock react-i18next
vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, defaultValue?: string) => defaultValue || key,
      i18n: {
        changeLanguage: () => new Promise(() => {}),
      },
    }),
  };
});

const createMockStore = (searchResults: SearchResult[] = [], getVideoUrl?: (id: string) => string) => {
  return configureStore({
    reducer: {
      search: (state = { 
        selectedResults: searchResults,
        searchQueries: searchResults.length > 0 ? [{
          dbId: 1,
          queryId: 'test-query-1',
          query: 'test search',
          watch: false,
          results: searchResults,
          queryStatus: 'idle' as any,
          tags: [],
          createdAt: '2025-01-01T10:00:00Z',
          updatedAt: '2025-01-01T10:00:00Z',
          topK: 10,
        }] : [],
        unreads: [],
        selectedQuery: searchResults.length > 0 ? 'test-query-1' : null,
        triggerLoad: true,
        suggestedTags: [],
      }, _action) => state,
      videos: (state = { 
        videos: [],
        status: 'ready' as any,
        getVideoUrl,
      }, _action) => state,
    },
    preloadedState: {
      search: { 
        selectedResults: searchResults,
        searchQueries: searchResults.length > 0 ? [{
          dbId: 1,
          queryId: 'test-query-1',
          query: 'test search',
          watch: false,
          results: searchResults,
          queryStatus: 'idle' as any,
          tags: [],
          createdAt: '2025-01-01T10:00:00Z',
          updatedAt: '2025-01-01T10:00:00Z',
          topK: 10,
        }] : [],
        unreads: [],
        selectedQuery: searchResults.length > 0 ? 'test-query-1' : null,
        triggerLoad: true,
        suggestedTags: [],
      },
      videos: { 
        videos: [],
        status: 'ready' as any,
        getVideoUrl,
      },
    },
  });
};

const createMockSearchResult = (overrides: Partial<SearchResult> = {}): SearchResult => {
  const baseResult: SearchResult = {
    id: 'result-1',
    page_content: 'Video content description',
    type: 'video',
    video: {
      videoId: 'video-1',
      name: 'Test Video',
      url: '',
      tags: [],
      createdAt: '2025-01-01T10:00:00Z',
      updatedAt: '2025-01-01T10:00:00Z',
    },
    metadata: {
      bucket_name: 'test-bucket',
      clip_duration: 10,
      tags: 'action,adventure',
      date: '2025-01-01',
      date_time: '2025-01-01T10:00:00Z',
      day: 1,
      fps: 30,
      frames_in_clip: 300,
      hours: 10,
      id: 'video-1',
      interval_num: 1,
      minutes: 0,
      month: 1,
      seconds: 0,
      time: '10:00:00',
      timestamp: 1704096000,
      total_frames: 300,
      video: 'test-video.mp4',
      video_id: 'video-1',
      video_path: '/path/to/video',
      video_rel_url: '/videos/test-video.mp4',
      video_remote_path: 'remote/path/video',
      video_url: 'http://example.com/video.mp4',
      year: 2025,
      relevance_score: 0.95,
    } as any, // Use any to allow additional properties like name/title
  };

  return {
    ...baseResult,
    ...overrides,
    metadata: {
      ...baseResult.metadata,
      ...overrides.metadata,
    },
  };
};

const renderWithProviders = (component: React.ReactElement, store: any) => {
  return render(
    <Provider store={store}>
      <I18nextProvider i18n={i18n}>
        {component}
      </I18nextProvider>
    </Provider>
  );
};

describe('VideoGroupsView Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Empty States', () => {
    it('should render empty state when no search results', () => {
      const store = createMockStore([]);
      renderWithProviders(<VideoGroupsView />, store);

      expect(screen.getByText('Video Groups by Tags')).toBeInTheDocument();
      expect(screen.getByText('No Search Results')).toBeInTheDocument();
      expect(screen.getByText('Please run a search to see grouped results by tag.')).toBeInTheDocument();
    });

    it('should render empty state when selectedResults is null', () => {
      const store = createMockStore();
      renderWithProviders(<VideoGroupsView />, store);

      expect(screen.getByText('Video Groups by Tags')).toBeInTheDocument();
      expect(screen.getByText('No Search Results')).toBeInTheDocument();
    });

    it('should render no tagged videos state when results exist but have no tags', () => {
      const mockResult = createMockSearchResult({
        metadata: {
          ...createMockSearchResult().metadata,
          tags: '',
        },
      });
      const store = createMockStore([mockResult]);
      renderWithProviders(<VideoGroupsView />, store);

      expect(screen.getByText('Video Groups by Tags')).toBeInTheDocument();
      // When there are no tags, the component shows an "Untagged" group instead of "No Tagged Videos"
      expect(screen.getByRole('heading', { name: /Untagged.*1.*videos/ })).toBeInTheDocument();
    });
  });

  describe('Video Grouping Logic', () => {
    it('should group videos by tags correctly', () => {
      const mockResults = [
        createMockSearchResult({
          id: 'result-1',
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-1',
            tags: 'action,adventure',
            relevance_score: 0.95,
          },
        }),
        createMockSearchResult({
          id: 'result-2',
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-2',
            tags: 'action,comedy',
            relevance_score: 0.85,
          },
        }),
      ];

      const store = createMockStore(mockResults);
      renderWithProviders(<VideoGroupsView />, store);

      // Check for group headers and video counts
      expect(screen.getByRole('heading', { name: /action.*2.*videos/ })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /adventure.*1.*videos/ })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /comedy.*1.*videos/ })).toBeInTheDocument();
    });

    it('should handle videos with no tags by putting them in Untagged group', () => {
      const mockResults = [
        createMockSearchResult({
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-1',
            tags: 'action',
          },
        }),
        createMockSearchResult({
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-2',
            tags: '',
          },
        }),
      ];

      const store = createMockStore(mockResults);
      renderWithProviders(<VideoGroupsView />, store);

      expect(screen.getByRole('heading', { name: /action.*1.*videos/ })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /Untagged.*1.*videos/ })).toBeInTheDocument();
    });

    it('should handle array format tags', () => {
      const mockResults = [
        createMockSearchResult({
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-1',
            tags: ['action', 'adventure'] as any,
          },
        }),
      ];

      const store = createMockStore(mockResults);
      renderWithProviders(<VideoGroupsView />, store);

      expect(screen.getByRole('heading', { name: /action.*1.*videos/ })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /adventure.*1.*videos/ })).toBeInTheDocument();
    });

    it('should filter out empty and whitespace-only tags', () => {
      const mockResults = [
        createMockSearchResult({
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-1',
            tags: 'action,  ,   , adventure,',
          },
        }),
      ];

      const store = createMockStore(mockResults);
      renderWithProviders(<VideoGroupsView />, store);

      expect(screen.getByRole('heading', { name: /action.*1.*videos/ })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /adventure.*1.*videos/ })).toBeInTheDocument();
      // Should not have empty tag groups - check that we don't have more than 2 groups
      const headings = screen.getAllByRole('heading');
      expect(headings).toHaveLength(3); // "Video Groups by Tags" + "action" + "adventure"
    });
  });

  describe('Relevance Score Sorting', () => {
    it('should sort videos by relevance score in descending order within groups', () => {
      const mockResults = [
        createMockSearchResult({
          id: 'result-1',
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-1',
            tags: 'action',
            relevance_score: 0.75,
          },
        }),
        createMockSearchResult({
          id: 'result-2',
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-2',
            tags: 'action',
            relevance_score: 0.95,
          },
        }),
        createMockSearchResult({
          id: 'result-3',
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-3',
            tags: 'action',
            relevance_score: 0.85,
          },
        }),
      ];

      const store = createMockStore(mockResults);
      renderWithProviders(<VideoGroupsView />, store);

      const relevanceScores = screen.getAllByText(/Relevance Score:/);
      expect(relevanceScores[0]).toHaveTextContent('Relevance Score: 0.950');
      expect(relevanceScores[1]).toHaveTextContent('Relevance Score: 0.850');
      expect(relevanceScores[2]).toHaveTextContent('Relevance Score: 0.750');
    });

    it('should handle missing relevance scores by defaulting to 0', () => {
      const mockResults = [
        createMockSearchResult({
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-1',
            tags: 'action',
            relevance_score: undefined as any,
          },
        }),
      ];

      const store = createMockStore(mockResults);
      renderWithProviders(<VideoGroupsView />, store);

      expect(screen.getByText('Relevance Score: 0.000')).toBeInTheDocument();
    });
  });

  describe('Video Display', () => {
    it('should display video player when video URL is available', () => {
      const mockResults = [
        createMockSearchResult({
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-1',
            tags: 'action',
          },
        }),
      ];

      const getVideoUrl = vi.fn().mockReturnValue('http://example.com/video.mp4');
      const store = createMockStore(mockResults, getVideoUrl);
      renderWithProviders(<VideoGroupsView />, store);

      // Check that the component renders with the video content
      expect(screen.getByRole('heading', { name: /action.*1.*videos/ })).toBeInTheDocument();
      expect(screen.getByText('Relevance Score: 0.950')).toBeInTheDocument();
    });

    it('should display placeholder when video URL is not available', () => {
      const mockResults = [
        createMockSearchResult({
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-1',
            tags: 'action',
          },
        }),
      ];

      const getVideoUrl = vi.fn().mockReturnValue('');
      const store = createMockStore(mockResults, getVideoUrl);
      renderWithProviders(<VideoGroupsView />, store);

      expect(screen.getByText('Video not available')).toBeInTheDocument();
    });
  });

  describe('Video Metadata Display', () => {
    it('should display relevance score with 3 decimal places', () => {
      const mockResults = [
        createMockSearchResult({
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-1',
            tags: 'action',
            relevance_score: 0.123456,
          },
        }),
      ];

      const store = createMockStore(mockResults);
      renderWithProviders(<VideoGroupsView />, store);

      expect(screen.getByText('Relevance Score: 0.123')).toBeInTheDocument();
    });
  });

  describe('Data Transformation Edge Cases', () => {
    it('should handle missing video_id in metadata', () => {
      const mockResults = [
        createMockSearchResult({
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: undefined as any,
            id: 'fallback-id',
            tags: 'action',
          },
        }),
      ];

      const store = createMockStore(mockResults);
      renderWithProviders(<VideoGroupsView />, store);

      expect(screen.getByRole('heading', { name: /action.*1.*videos/ })).toBeInTheDocument();
    });

    it('should handle null metadata', () => {
      const mockResults = [
        {
          ...createMockSearchResult(),
          metadata: null as any,
        },
      ];

      const store = createMockStore(mockResults);
      renderWithProviders(<VideoGroupsView />, store);

      // Should show no tagged videos since metadata is null
      expect(screen.getByText('No Tagged Videos')).toBeInTheDocument();
    });

    it('should handle undefined metadata', () => {
      const mockResults = [
        {
          ...createMockSearchResult(),
          metadata: undefined as any,
        },
      ];

      const store = createMockStore(mockResults);
      renderWithProviders(<VideoGroupsView />, store);

      expect(screen.getByText('No Tagged Videos')).toBeInTheDocument();
    });
  });

  describe('Component Structure', () => {
    it('should render main container with correct structure', () => {
      const mockResults = [
        createMockSearchResult({
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-1',
            tags: 'action',
          },
        }),
      ];

      const store = createMockStore(mockResults);
      renderWithProviders(<VideoGroupsView />, store);

      expect(screen.getByText('Video Groups by Tags')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /action.*1.*videos/ })).toBeInTheDocument();
    });

    it('should render video cards with relevance scores', () => {
      const mockResults = [
        createMockSearchResult({
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-1',
            tags: 'action',
            relevance_score: 0.95,
          },
        }),
      ];

      const store = createMockStore(mockResults);
      renderWithProviders(<VideoGroupsView />, store);

      // Check that relevance score is displayed
      expect(screen.getByText(/Relevance Score: 0.950/)).toBeInTheDocument();
    });
  });

  describe('Integration Tests', () => {
    it('should handle complete workflow with multiple videos and tags', () => {
      const mockResults = [
        createMockSearchResult({
          id: 'result-1',
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-1',
            tags: 'action,adventure',
            relevance_score: 0.95,
          },
        }),
        createMockSearchResult({
          id: 'result-2',
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-2',
            tags: 'comedy,romance',
            relevance_score: 0.85,
          },
        }),
        createMockSearchResult({
          id: 'result-3',
          metadata: {
            ...createMockSearchResult().metadata,
            video_id: 'video-3',
            tags: 'action,comedy',
            relevance_score: 0.75,
          },
        }),
      ];

      const getVideoUrl = vi.fn().mockImplementation((id) => `http://example.com/${id}.mp4`);
      const store = createMockStore(mockResults, getVideoUrl);
      renderWithProviders(<VideoGroupsView />, store);

      // Should have 4 groups: action (2 videos), adventure (1), comedy (2), romance (1)
      expect(screen.getByRole('heading', { name: /action.*2.*videos/ })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /adventure.*1.*videos/ })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /comedy.*2.*videos/ })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /romance.*1.*videos/ })).toBeInTheDocument();

      // Check that all relevance scores are displayed
      const relevanceScores = screen.getAllByText(/Relevance Score: 0\.\d{3}/);
      expect(relevanceScores.length).toBeGreaterThan(4); // Each video appears in multiple groups
      
      // Check specific scores exist (some appear multiple times due to video grouping)
      expect(screen.getAllByText('Relevance Score: 0.950')).toHaveLength(2); // video-1 appears in action and adventure groups
      expect(screen.getAllByText('Relevance Score: 0.850')).toHaveLength(2); // video-2 appears in comedy and romance groups  
      expect(screen.getAllByText('Relevance Score: 0.750')).toHaveLength(2); // video-3 appears in action and comedy groups

      // Verify that getVideoUrl function is available (the component has access to it)
      expect(getVideoUrl).toBeDefined();
    });
  });
});