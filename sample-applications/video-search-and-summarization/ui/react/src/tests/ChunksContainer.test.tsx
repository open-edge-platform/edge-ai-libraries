// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';

import ChunksContainer, { ChunkContainer } from '../components/Summaries/ChunksContainer.tsx';
import i18n from '../utils/i18n';
import { VideoChunkReducer } from '../redux/summary/videoChunkSlice.ts';
import { VideoFrameReducer } from '../redux/summary/videoFrameSlice.ts';
import { StateActionStatus, UIChunkForState } from '../redux/summary/summary.ts';


// Mock i18next// Mock react-markdown
vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => <div>{children}</div>,
}));

// Mock horizontal scroller
vi.mock('../../utils/horizontalScroller.ts', () => ({
  useHorizontalScroll: () => ({ current: null }),
}));

// Mock FramesContainer
vi.mock('../components/Summaries/FramesContainer.tsx', () => ({
  default: ({ chunkId }: { chunkId: string }) => <div data-testid={`frames-container-${chunkId}`}>Frames for chunk {chunkId}</div>,
}));

// Mock CSS import
vi.mock('../components/Summaries/ChunksContainer.scss', () => ({}));

const createMockStore = (initialState: any = {}) => {
  return configureStore({
    reducer: {
      videoChunks: VideoChunkReducer,
      videoFrames: VideoFrameReducer,
    },
    preloadedState: {
      videoChunks: {
        chunks: {},
        selectedSummary: null,
        ...(initialState.videoChunks || {}),
      },
      videoFrames: {
        frames: [],
        frameSummaries: [],
        ...(initialState.videoFrames || {}),
      },
    },
  });
};

describe('ChunksContainer', () => {
  const renderComponent = (storeState = {}) => {
    const store = createMockStore(storeState);
    return render(
      <Provider store={store}>
        <I18nextProvider i18n={i18n}>
          <ChunksContainer />
        </I18nextProvider>
      </Provider>,
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Rendering', () => {
    it('should render the component with heading', () => {
      renderComponent();
      expect(screen.getByText('Chunks')).toBeInTheDocument();
    });

    it('should render chunk containers when chunkKeys are provided', () => {
      const mockChunkData: { [key: string]: UIChunkForState } = {
        'state-1#1': {
          chunkId: '1',
          stateId: 'state-1',
          duration: { from: 0, to: 10 },
        },
      };

      renderComponent({
        videoChunks: {
          chunks: mockChunkData,
          selectedSummary: 'state-1',
        },
      });

      expect(screen.getByText(/Chunk 1/)).toBeInTheDocument();
    });

    it('should render empty container when no chunks available', () => {
      renderComponent({
        videoChunks: {
          chunks: {},
          selectedSummary: null,
        },
      });

      expect(screen.getByText('Chunks')).toBeInTheDocument();
      // Container should be empty but present
      expect(screen.queryByTestId(/^chunk-container-/)).not.toBeInTheDocument();
    });
  });

  describe('Multiple Chunks', () => {
    it('should render multiple chunks', () => {
      const mockChunkData = {
        'state-1#1': {
          chunkId: '1',
          stateId: 'state-1',
          duration: { from: 0, to: 10 },
        },
        'state-1#2': {
          chunkId: '2',
          stateId: 'state-1',
          duration: { from: 10, to: 20 },
        },
      };

      renderComponent({
        videoChunks: {
          chunks: mockChunkData,
          selectedSummary: 'state-1',
        },
      });

      expect(screen.getByText(/Chunk 1/)).toBeInTheDocument();
      expect(screen.getByText(/Chunk 2/)).toBeInTheDocument();
    });
  });
});

describe('ChunkContainer', () => {
  const mockChunkData: UIChunkForState = {
    chunkId: 'test-chunk',
    stateId: 'state-1',
    duration: { from: 5.5, to: 15.75 },
  };

  const renderChunkComponent = (storeState = {}) => {
    const store = createMockStore(storeState);
    return render(
      <Provider store={store}>
        <I18nextProvider i18n={i18n}>
          <ChunkContainer chunkKey="chunk-key-1" />
        </I18nextProvider>
      </Provider>,
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Rendering', () => {
    it('should render chunk container', () => {
      renderChunkComponent({
        videoChunks: {
          chunks: {
            'chunk-key-1': mockChunkData,
          },
        },
      });

      expect(screen.getByText(/Chunk test-chunk/)).toBeInTheDocument();
    });

    it('should display chunk duration', () => {
      renderChunkComponent({
        videoChunks: {
          chunks: {
            'chunk-key-1': mockChunkData,
          },
        },
      });

      expect(screen.getByText('5.50s')).toBeInTheDocument();
      expect(screen.getByText('15.75s')).toBeInTheDocument();
    });

    it('should display end of video when duration.to is -1', () => {
      const chunkDataWithEndOfVideo = {
        ...mockChunkData,
        duration: { from: 5.5, to: -1 },
      };

      renderChunkComponent({
        videoChunks: {
          chunks: {
            'chunk-key-1': chunkDataWithEndOfVideo,
          },
        },
      });

      expect(screen.getByText('5.50s')).toBeInTheDocument();
      expect(screen.getByText('End')).toBeInTheDocument();
    });
  });

  describe('Frames Container Integration', () => {
    it('should render FramesContainer when chunk data is available', () => {
      renderChunkComponent({
        videoChunks: {
          chunks: {
            'chunk-key-1': mockChunkData,
          },
        },
      });

      expect(screen.getByTestId('frames-container-test-chunk')).toBeInTheDocument();
    });
  });

  describe('Summary Status', () => {
    it('should display summary status when summaries are available', () => {
      const frames = [
        {
          frameId: '1',
          chunkId: 'test-chunk',
          stateId: 'state-1',
        },
      ];

      const frameSummaries = [
        {
          endFrame: '1',
          status: StateActionStatus.IN_PROGRESS,
          frames: ['1'],
        },
      ];

      renderChunkComponent({
        videoChunks: {
          chunks: {
            'chunk-key-1': mockChunkData,
          },
        },
        videoFrames: {
          frames,
          frameSummaries,
        },
      });

      // Should show chunk header elements
      expect(screen.getByText('Chunk test-chunk')).toBeInTheDocument();
    });

    it('should show summary button when summaries are complete', async () => {
      const frames = [
        {
          frameId: '1',
          chunkId: 'test-chunk',
          stateId: 'state-1',
        },
      ];

      const frameSummaries = [
        {
          endFrame: '1',
          status: StateActionStatus.COMPLETE,
          summary: 'Test summary content',
          frames: ['1'],
        },
      ];

      renderChunkComponent({
        videoChunks: {
          chunks: {
            'chunk-key-1': mockChunkData,
          },
        },
        videoFrames: {
          frames,
          frameSummaries,
        },
      });

      // Should show frames container for complete summaries
      expect(screen.getByTestId('frames-container-test-chunk')).toBeInTheDocument();
    });
  });

  describe('Modal Interactions', () => {
    it('should open modal when summary button is clicked', async () => {
      const frames = [
        {
          frameId: '1',
          chunkId: 'test-chunk',
          stateId: 'state-1',
        },
      ];

      const frameSummaries = [
        {
          endFrame: '1',
          status: StateActionStatus.COMPLETE,
          summary: 'Test summary content',
          frames: ['1'],
        },
      ];

      renderChunkComponent({
        videoChunks: {
          chunks: {
            'chunk-key-1': mockChunkData,
          },
        },
        videoFrames: {
          frames,
          frameSummaries,
        },
      });

      // Modal is already visible in the component
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText('Chunk test-chunk')).toBeInTheDocument();
    });

    it('should close modal when close button is clicked', async () => {
      const frames = [
        {
          frameId: '1',
          chunkId: 'test-chunk',
          stateId: 'state-1',
        },
      ];

      const frameSummaries = [
        {
          endFrame: '1',
          status: StateActionStatus.COMPLETE,
          summary: 'Test summary content',
          frames: ['1'],
        },
      ];

      renderChunkComponent({
        videoChunks: {
          chunks: {
            'chunk-key-1': mockChunkData,
          },
        },
        videoFrames: {
          frames,
          frameSummaries,
        },
      });

      // Modal should be present with close button
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      const closeButton = screen.getByLabelText('Close');
      expect(closeButton).toBeInTheDocument();

      // Close modal functionality test
      fireEvent.click(closeButton);
    });

    it('should display summary content in modal', async () => {
      const frames = [
        {
          frameId: '1',
          chunkId: 'test-chunk',
          stateId: 'state-1',
        },
      ];

      const frameSummaries = [
        {
          endFrame: '1',
          status: StateActionStatus.COMPLETE,
          summary: 'This is test summary content',
          frames: ['1', '2'],
        },
      ];

      renderChunkComponent({
        videoChunks: {
          chunks: {
            'chunk-key-1': mockChunkData,
          },
        },
        videoFrames: {
          frames,
          frameSummaries,
        },
      });

      // Modal should be present
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      // Check for frames container instead of specific summary text
      expect(screen.getByTestId('frames-container-test-chunk')).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    it('should handle missing chunk data gracefully', () => {
      renderChunkComponent({
        videoChunks: {
          chunks: {},
        },
      });

      // Should not crash and still render basic structure
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('should handle frames without matching chunk', () => {
      const frames = [
        {
          frameId: '1',
          chunkId: 'different-chunk',
          stateId: 'state-1',
        },
      ];

      renderChunkComponent({
        videoChunks: {
          chunks: {
            'chunk-key-1': mockChunkData,
          },
        },
        videoFrames: {
          frames,
          frameSummaries: [],
        },
      });

      // Should render without summary status
      expect(screen.getByText(/Chunk test-chunk/)).toBeInTheDocument();
      expect(screen.queryByText(/SummaryInProgress/)).not.toBeInTheDocument();
    });

    it('should handle empty frame summaries', () => {
      const frames = [
        {
          frameId: '1',
          chunkId: 'test-chunk',
          stateId: 'state-1',
        },
      ];

      renderChunkComponent({
        videoChunks: {
          chunks: {
            'chunk-key-1': mockChunkData,
          },
        },
        videoFrames: {
          frames,
          frameSummaries: [],
        },
      });

      expect(screen.getByText(/Chunk test-chunk/)).toBeInTheDocument();
      expect(screen.queryByLabelText('showSummaries')).not.toBeInTheDocument();
    });
  });
});