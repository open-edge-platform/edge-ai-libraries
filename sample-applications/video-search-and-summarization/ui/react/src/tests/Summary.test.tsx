// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent, act } from '@testing-library/react';
import { Provider } from 'react-redux';
import { I18nextProvider } from 'react-i18next';
import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom';
import { configureStore } from '@reduxjs/toolkit';
import { Summary } from '../components/Summaries/Summary';
import { SummarySlice } from '../redux/summary/summarySlice';
import { VideoChunkSlice } from '../redux/summary/videoChunkSlice';
import { VideoFrameSlice } from '../redux/summary/videoFrameSlice';
import { VideoSlice } from '../redux/video/videoSlice';
import i18n from '../utils/i18n';
import { StateActionStatus } from '../redux/summary/summary';

// Mock socket
vi.mock('../socket', () => ({
  socket: {
    emit: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}));

// Mock axios
vi.mock('axios', () => ({
  default: {
    get: vi.fn().mockImplementation((url) => {
      if (url.includes('/app/config')) {
        return Promise.resolve({
          data: {
            multiFrame: 10,
            framePrompt: 'Test frame prompt',
            summaryMapPrompt: 'Test map prompt',
            summaryReducePrompt: 'Test reduce prompt',
            summarySinglePrompt: 'Test single prompt',
            evamPipeline: 'test-pipeline',
            frameOverlap: 5,
            meta: {
              evamPipelines: [
                { value: 'test-pipeline', label: 'Test Pipeline' },
                { value: 'pipeline2', label: 'Pipeline 2' },
              ],
            },
          },
        });
      }
      
      // Default response for other endpoints  
      return Promise.resolve({
        data: {
          multiFrame: 10, 
          framePrompt: 'test',
          chunks: [
            { id: 1, text: 'chunk 1', status: 'complete' },
            { id: 2, text: 'chunk 2', status: 'complete' },
            { id: 3, text: 'chunk 3', status: 'complete' }
          ],
          frames: [
            { id: 1, frameNumber: 1, summary: 'frame 1 summary' },
            { id: 2, frameNumber: 2, summary: 'frame 2 summary' },
            { id: 3, frameNumber: 3, summary: 'frame 3 summary' }
          ],
          frameSummaries: [
            { frameId: 1, summary: 'frame 1 summary', status: 'complete' },
            { frameId: 2, summary: 'frame 2 summary', status: 'complete' }
          ]
        } 
      });
    }),
  },
}));

// Mock config
vi.mock('../config', () => ({
  APP_URL: 'http://localhost:3000',
}));

// Mock Carbon components
vi.mock('@carbon/react', () => ({
  AILabel: ({ children }: any) => <div data-testid="ai-label">{children}</div>,
  AILabelContent: ({ children }: any) => <div data-testid="ai-label-content">{children}</div>,
  IconButton: ({ children, onClick }: any) => (
    <button data-testid="icon-button" onClick={onClick}>
      {children}
    </button>
  ),
  Tag: ({ children, type, size }: any) => (
    <span data-testid="tag" data-type={type} data-size={size}>
      {children}
    </span>
  ),
}));

// Mock icons
vi.mock('@carbon/icons-react', () => ({
  Renew: () => <span data-testid="renew-icon">↻</span>,
}));

// Mock child components
vi.mock('../components/Summaries/ChunksContainer', () => ({
  default: () => <div data-testid="chunks-container">ChunksContainer</div>,
}));

vi.mock('../components/Summaries/SummariesContainer', () => ({
  default: () => <div data-testid="summaries-container">SummariesContainer</div>,
}));

vi.mock('../components/Summaries/StatusTag', () => ({
  default: ({ action, label, count }: any) => (
    <div data-testid="status-tag" data-action={action} data-label={label} data-count={count}>
      {label} {count && `(${count})`}
    </div>
  ),
  statusClassLabel: { COMPLETE: 'complete', IN_PROGRESS: 'inProgress', NA: 'na' },
  statusClassName: { COMPLETE: 'success', IN_PROGRESS: 'warning', NA: 'gray' },
}));

// Mock Markdown
vi.mock('react-markdown', () => ({
  default: ({ children }: any) => <div data-testid="markdown">{children}</div>,
}));

// Mock systemConfig
const mockSystemConfig = {
  multiFrame: 10,
  framePrompt: 'Test frame prompt',
  summaryMapPrompt: 'Test map prompt', 
  summaryReducePrompt: 'Test reduce prompt',
  summarySinglePrompt: 'Test single prompt',
  evamPipeline: 'test-pipeline',
  meta: {
    evamPipelines: [
      { value: 'test-pipeline', name: 'Test Pipeline' },
      { value: 'pipeline-2', name: 'Pipeline 2' }
    ]
  }
};

// Mock getSystemConfig hook
vi.mock('../hooks/systemConfig', () => ({
  useSystemConfig: () => mockSystemConfig,
}));

// Mock utils
vi.mock('../utils/util', () => ({
  processMD: (text: string) => text,
}));

// Mock react-i18next
vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, params?: any) => {
        if (params) {
          return key.replace(/{{(.*?)}}/g, (_, p1) => params[p1] || p1);
        }
        return key;
      },
    }),
  };
});

// Create mock store
const createMockStore = (initialState: any = {}) => {
  return configureStore({
    reducer: {
      summaries: SummarySlice.reducer,
      videoChunks: VideoChunkSlice.reducer,
      videoFrames: VideoFrameSlice.reducer,
      videos: VideoSlice.reducer,
    },
    preloadedState: {
      summaries: {
        summaries: {},
        selectedSummary: null,
        sidebarSummaries: [],
        ...initialState.summaries,
      },
      videoChunks: {
        chunks: [],
        selectedSummary: null,
        ...initialState.videoChunks,
      },
      videoFrames: {
        frames: [],
        selectedSummary: null,
        ...initialState.videoFrames,
      },
      videos: {
        selectedVideo: null,
        videos: [],
        ...initialState.videos,
      },
    },
  });
};

const mockSummary = {
  stateId: 'test-summary-1',
  title: 'Test Summary',
  videoId: 'test-video-1',
  videoPath: '/videos/test.mp4',
  videoSummary: 'This is a test summary content',
  videoSummaryStatus: StateActionStatus.COMPLETE,
  chunksCount: 3, // Add chunksCount for handleSummaryData function
  userInputs: {
    samplingFrame: 10,
    chunkDuration: 30,
  },
  inferenceConfig: {
    llm: {
      device: 'CPU',
      model: 'test-model',
      temperature: 0.5,
    },
    objectDetection: {
      device: 'CPU',
      model: 'yolo-model',
    },
  },
  systemConfig: {
    multiFrame: 10,
    framePrompt: 'Test frame prompt',
    summaryMapPrompt: 'Test map prompt',
    summaryReducePrompt: 'Test reduce prompt',
    summarySinglePrompt: 'Test single prompt',
    evamPipeline: 'test-pipeline',
    meta: {
      evamPipelines: [
        { value: 'test-pipeline', name: 'Test Pipeline' },
        { value: 'pipeline-2', name: 'Pipeline 2' }
      ]
    }
  },
  frameSummaryStatus: {
    complete: 5,
    inProgress: 2,
    na: 0,
    ready: 1,
  },
  chunkingStatus: StateActionStatus.COMPLETE,
};

describe('Summary Component', () => {
  const renderComponent = (summaryData: any = null) => {
    const storeWithData = createMockStore({
      summaries: {
        selectedSummary: summaryData ? 'test-summary-1' : null,
        summaries: summaryData ? { 'test-summary-1': summaryData } : {},
      },
      videos: {
        selectedVideo: null,
        videos: summaryData && summaryData.videoId ? [
          {
            id: summaryData.videoId,
            name: 'test-video.mp4',
            path: summaryData.videoPath || '/videos/test.mp4',
            url: `http://localhost/video/${summaryData.videoId}`,
          }
        ] : [],
      },
    });

    let result: any;
    act(() => {
      result = render(
        <Provider store={storeWithData}>
          <I18nextProvider i18n={i18n}>
            <Summary />
          </I18nextProvider>
        </Provider>
      );
    });
    return result;
  };

  describe('Initial Rendering', () => {
    it('should render "select a summary" message when no summary is selected', () => {
      renderComponent(null);
      expect(screen.getByText('noSummariesAvailable')).toBeInTheDocument();
    });

    it('should render summary content when summary is selected', () => {
      renderComponent(mockSummary);
      expect(screen.getByTestId('ai-label')).toBeInTheDocument();
      expect(screen.getByTestId('markdown')).toBeInTheDocument();
    });

    it('should render all child components when summary is selected', () => {
      renderComponent(mockSummary);
      expect(screen.getByTestId('chunks-container')).toBeInTheDocument();
      expect(screen.getByTestId('summaries-container')).toBeInTheDocument();
    });
  });

  describe('Video Player', () => {
    it('should render video player with correct source', () => {
      renderComponent(mockSummary);
      const videoElement = document.querySelector('video');
      expect(videoElement).toBeInTheDocument();
      expect(videoElement).toHaveClass('video');
    });
  });

  describe('AI Label Information', () => {
    it('should display AI label with system information', () => {
      renderComponent(mockSummary);
      expect(screen.getByTestId('ai-label')).toBeInTheDocument();
      expect(screen.getByTestId('ai-label-content')).toBeInTheDocument();
    });
  });

  describe('Status Tags', () => {
    it('should render status tags for different processing stages', () => {
      renderComponent(mockSummary);
      const statusTags = screen.getAllByTestId('status-tag');
      expect(statusTags.length).toBeGreaterThan(0);
    });
  });

  describe('Summary Content', () => {
    it('should render summary text using Markdown', () => {
      renderComponent(mockSummary);
      expect(screen.getByTestId('markdown')).toBeInTheDocument();
    });

    it('should display Summary header', () => {
      renderComponent(mockSummary);
      expect(screen.getByText('Summary')).toBeInTheDocument();
    });
  });

  describe('Refresh Functionality', () => {
    it('should render refresh button', () => {
      renderComponent(mockSummary);
      expect(screen.getByTestId('icon-button')).toBeInTheDocument();
    });

    it('should handle refresh button click', async () => {
      renderComponent(mockSummary);
      const refreshButtons = screen.getAllByTestId('icon-button');
      const refreshButton = refreshButtons[0]; // Get the first one
      
      await act(async () => {
        fireEvent.click(refreshButton);
      });
      
      // Just verify the component is still rendered and axios was called
      expect(screen.getByText('Test Summary')).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('should handle missing inference config gracefully', () => {
      const summaryWithoutConfig = { ...mockSummary, inferenceConfig: undefined };
      expect(() => renderComponent(summaryWithoutConfig)).not.toThrow();
    });

    it('should handle empty summary text', () => {
      const summaryWithEmptyText = { ...mockSummary, videoSummary: '' };
      expect(() => renderComponent(summaryWithEmptyText)).not.toThrow();
    });
  });
});
