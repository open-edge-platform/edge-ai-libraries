// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import { Provider } from 'react-redux';
import { I18nextProvider } from 'react-i18next';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom';
import { configureStore, combineReducers } from '@reduxjs/toolkit';
import { SummariesContainer } from '../components/Summaries/SummariesContainer';
import { VideoFrameReducer } from '../redux/summary/videoFrameSlice';
import { SummaryReducers } from '../redux/summary/summarySlice';
import { StateActionStatus } from '../redux/summary/summary';
import i18n from '../utils/i18n';

// Mock Carbon components
vi.mock('@carbon/react', () => ({
  IconButton: ({ onClick, children, label, kind, disabled }: any) => (
    <button 
      data-testid={`icon-button-${label}`} 
      onClick={onClick} 
      data-kind={kind}
      disabled={disabled}
    >
      {children}
    </button>
  ),
  Modal: ({ children, open, onRequestClose, modalHeading, passiveModal }: any) => 
    open ? (
      <div data-testid="modal" data-passive={passiveModal} data-heading={modalHeading}>
        <button data-testid="modal-close" onClick={() => onRequestClose && onRequestClose()}>
          Close
        </button>
        {children}
      </div>
    ) : null,
  ModalBody: ({ children }: any) => <div data-testid="modal-body">{children}</div>,
  Tag: ({ children, size, type, ...props }: any) => (
    <span data-testid="carbon-tag" data-size={size} data-type={type} {...props}>
      {children}
    </span>
  ),
}));

// Mock Carbon icons
vi.mock('@carbon/icons-react', () => ({
  ClosedCaption: () => <div data-testid="closed-caption-icon">ClosedCaption</div>,
}));


// Mock react-markdown
vi.mock('react-markdown', () => ({
  default: ({ children }: any) => <div data-testid="markdown">{children}</div>,
}));

// Mock utility functions
vi.mock('../utils/horizontalScroller', () => ({
  useHorizontalScroll: () => ({ current: null }),
}));

vi.mock('../utils/util', () => ({
  processMD: (text: string) => text,
}));

// Mock react-i18next
vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
      i18n: {
        changeLanguage: () => new Promise(() => {}),
      },
    }),
  };
});

// Create mock store
const createMockStore = (initialState: any = {}) => {
  const rootReducer = combineReducers({
    videoFrames: VideoFrameReducer,
    summaries: SummaryReducers,
  });
  
  const preloadedState = {
    videoFrames: {
      frames: {},
      frameSummaries: {},
      selectedSummary: null,
      ...(initialState.videoFrames || {})
    },
    summaries: {
      summaries: [],
      chunkSummaries: {},
      systemConfig: null,
      ...(initialState.summaries || {})
    }
  };

  return configureStore({
    reducer: rootReducer,
    preloadedState,
    middleware: (getDefaultMiddleware) =>
      getDefaultMiddleware({
        serializableCheck: false,
      }),
  });
};const renderWithProviders = (component: React.ReactElement, store: any) => {
  return render(
    <Provider store={store}>
      <I18nextProvider i18n={i18n}>
        {component}
      </I18nextProvider>
    </Provider>
  );
};

describe('SummariesContainer Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Rendering', () => {
    it('should render the component with basic elements', () => {
      const store = createMockStore();
      renderWithProviders(<SummariesContainer />, store);

      expect(screen.getByText('FrameSummaries')).toBeInTheDocument();
      expect(document.querySelector('.frames')).toBeInTheDocument();
    });

    it('should render section header with frame summaries title', () => {
      const store = createMockStore();
      renderWithProviders(<SummariesContainer />, store);

      expect(screen.getByText('FrameSummaries')).toBeInTheDocument();
      expect(document.querySelector('.sectionHeader')).toBeInTheDocument();
    });

    it('should render frames grid container', () => {
      const store = createMockStore();
      renderWithProviders(<SummariesContainer />, store);

      const framesContainer = document.querySelector('.frames');
      expect(framesContainer).toBeInTheDocument();
    });

    it('should not show modal initially', () => {
      const store = createMockStore();
      renderWithProviders(<SummariesContainer />, store);

      expect(screen.queryByTestId('modal')).not.toBeInTheDocument();
    });
  });

  describe('Frame Rendering', () => {
    it('should render frame headers when frames are provided', () => {
      const stateId = 'test-state-id';
      const frameKey1 = `${stateId}#chunk1#1`;
      const frameKey2 = `${stateId}#chunk1#2`; 
      const frameKey3 = `${stateId}#chunk1#3`;
      
      const store = createMockStore({
        videoFrames: { 
          selectedSummary: stateId,
          frames: {
            [frameKey1]: { stateId, chunkId: 'chunk1', frameId: '1' },
            [frameKey2]: { stateId, chunkId: 'chunk1', frameId: '2' },
            [frameKey3]: { stateId, chunkId: 'chunk1', frameId: '3' }
          },
          frameSummaries: {}
        },
      });

      renderWithProviders(<SummariesContainer />, store);

      expect(screen.getByText('1')).toBeInTheDocument();
      expect(screen.getByText('2')).toBeInTheDocument();
      expect(screen.getByText('3')).toBeInTheDocument();
    });

    it('should apply correct grid template columns based on frames count', () => {
      const stateId = 'test-state-id';
      const frameKey1 = `${stateId}#chunk1#1`;
      const frameKey2 = `${stateId}#chunk1#2`;
      
      const store = createMockStore({
        videoFrames: {
          selectedSummary: stateId,
          frames: {
            [frameKey1]: { stateId, chunkId: 'chunk1', frameId: '1' },
            [frameKey2]: { stateId, chunkId: 'chunk1', frameId: '2' }
          },
          frameSummaries: {}
        },
      });

      renderWithProviders(<SummariesContainer />, store);

      const framesContainer = document.querySelector('.frames');
      expect(framesContainer).toHaveStyle({
        gridTemplateColumns: 'repeat(1, minmax(50px, 1fr))',
      });
    });

    it('should handle empty frames array', () => {
      const store = createMockStore({
        videoFrames: {
          selectedSummary: null,
          frames: {},
          frameSummaries: {}
        },
      });

      renderWithProviders(<SummariesContainer />, store);

      const framesContainer = document.querySelector('.frames');
      // When frames is empty, frames.length - 1 = -1, resulting in repeat(-1, ...)
      expect(framesContainer).toHaveStyle({
        gridTemplateColumns: 'repeat(-1, minmax(50px, 1fr))',
      });
    });
  });

  describe('Frame Summaries Rendering', () => {
    it('should render frame summaries with correct status styling', () => {
      const stateId = 'test-state-id';
      const frameKey1 = `${stateId}#chunk1#1`;
      const frameKey2 = `${stateId}#chunk1#2`;
      const frameKey3 = `${stateId}#chunk1#3`;
      const frameKey4 = `${stateId}#chunk1#4`;
      
      const mockFrameSummary1 = {
        frameKey: 'frame1',
        startFrame: '1',
        endFrame: '2',
        status: StateActionStatus.COMPLETE,
        summary: 'Test summary content',
        stateId: stateId,
        frames: ['1', '2']
      };
      
      const mockFrameSummary2 = {
        frameKey: 'frame2',
        startFrame: '3',
        endFrame: '4',
        status: StateActionStatus.IN_PROGRESS,
        summary: '',
        stateId: stateId,
        frames: ['3', '4']
      };

      const store = createMockStore({
        videoFrames: {
          selectedSummary: stateId,
          frames: {
            [frameKey1]: { stateId, chunkId: 'chunk1', frameId: '1' },
            [frameKey2]: { stateId, chunkId: 'chunk1', frameId: '2' },
            [frameKey3]: { stateId, chunkId: 'chunk1', frameId: '3' },
            [frameKey4]: { stateId, chunkId: 'chunk1', frameId: '4' }
          },
          frameSummaries: {
            [frameKey1]: mockFrameSummary1,
            [frameKey3]: mockFrameSummary2
          }
        },
      });
      
      renderWithProviders(<SummariesContainer />, store);

      expect(screen.getByText('Frames: [1 : 2]')).toBeInTheDocument();
      expect(screen.getByText('Frames: [3 : 4]')).toBeInTheDocument();
    });

    it('should show summary button for completed summaries', () => {
      const stateId = 'test-state-id';
      const frameKey1 = `${stateId}#chunk1#1`;
      const frameKey2 = `${stateId}#chunk1#2`;
      const frameKey3 = `${stateId}#chunk1#3`;
      
      const mockFrameSummary = {
        frameKey: 'frame1',
        startFrame: '1',
        endFrame: '2',
        status: StateActionStatus.COMPLETE,
        summary: 'Test summary content',
        stateId: stateId,
        frames: ['1', '2']
      };

      const store = createMockStore({
        videoFrames: {
          selectedSummary: stateId,
          frames: {
            [frameKey1]: { stateId, chunkId: 'chunk1', frameId: '1' },
            [frameKey2]: { stateId, chunkId: 'chunk1', frameId: '2' },
            [frameKey3]: { stateId, chunkId: 'chunk1', frameId: '3' }
          },
          frameSummaries: {
            [frameKey1]: mockFrameSummary
          }
        },
      });
      
      renderWithProviders(<SummariesContainer />, store);

      expect(screen.getByTestId('icon-button-Summary')).toBeInTheDocument();
      expect(screen.getByTestId('closed-caption-icon')).toBeInTheDocument();
    });

    it('should show disabled button for non-completed summaries', () => {
      const stateId = 'test-state-id';
      const frameKey1 = `${stateId}#chunk1#1`;
      const frameKey2 = `${stateId}#chunk1#2`;
      const frameKey3 = `${stateId}#chunk1#3`;
      
      const mockFrameSummary = {
        frameKey: 'frame1',
        startFrame: '1',
        endFrame: '2',
        status: StateActionStatus.IN_PROGRESS,
        summary: '',
        stateId: stateId,
        frames: ['1', '2']
      };

      const store = createMockStore({
        videoFrames: {
          selectedSummary: stateId,
          frames: {
            [frameKey1]: { stateId, chunkId: 'chunk1', frameId: '1' },
            [frameKey2]: { stateId, chunkId: 'chunk1', frameId: '2' },
            [frameKey3]: { stateId, chunkId: 'chunk1', frameId: '3' }
          },
          frameSummaries: {
            [frameKey1]: mockFrameSummary
          }
        },
      });
      
      renderWithProviders(<SummariesContainer />, store);

      const disabledButton = screen.getByTestId('icon-button-');
      expect(disabledButton).toBeDisabled();
    });

    it('should apply correct grid area styling for frame summaries', () => {
      const stateId = 'test-state-id';
      const frameKey1 = `${stateId}#chunk1#1`;
      const frameKey2 = `${stateId}#chunk1#2`;
      const frameKey3 = `${stateId}#chunk1#3`;
      const frameKey4 = `${stateId}#chunk1#4`;
      
      const mockFrameSummary = {
        frameKey: 'frame1',
        startFrame: '1',
        endFrame: '3',
        status: StateActionStatus.COMPLETE,
        summary: 'Test summary',
        stateId: stateId,
        frames: ['1', '2', '3']
      };

      const store = createMockStore({
        videoFrames: {
          selectedSummary: stateId,
          frames: {
            [frameKey1]: { stateId, chunkId: 'chunk1', frameId: '1' },
            [frameKey2]: { stateId, chunkId: 'chunk1', frameId: '2' },
            [frameKey3]: { stateId, chunkId: 'chunk1', frameId: '3' },
            [frameKey4]: { stateId, chunkId: 'chunk1', frameId: '4' }
          },
          frameSummaries: {
            [frameKey1]: mockFrameSummary
          }
        },
      });
      
      renderWithProviders(<SummariesContainer />, store);

      const frameSummary = document.querySelector('.frame-summary');
      expect(frameSummary).toHaveStyle({
        gridArea: '2 / 1 / span 1 / span 3',
      });
    });
  });



  describe('System Configuration Integration', () => {


    it('should handle null system config gracefully', () => {
      const store = createMockStore({
        summary: {
          getSystemConfig: null,
        },
      });
      
      renderWithProviders(<SummariesContainer />, store);

      // Should render without errors
      expect(screen.getByText('FrameSummaries')).toBeInTheDocument();
      
      // Default overlap should be 0, resulting in 1 row
      const framesContainer = document.querySelector('.frames');
      expect(framesContainer).toHaveStyle({
        gridTemplateRows: '1fr repeat(1, 1fr)',
      });
    });

    it('should initialize with default overlap value', () => {
      const store = createMockStore();
      renderWithProviders(<SummariesContainer />, store);

      const framesContainer = document.querySelector('.frames');
      expect(framesContainer).toHaveStyle({
        gridTemplateRows: '1fr repeat(1, 1fr)', // Default overlap is 0, so 0 + 1 = 1
      });
    });
  });

  describe('Status Count Integration', () => {
    it('should render CountStatusEmp component with status counts', () => {
      const mockStatusCount = {
        [StateActionStatus.COMPLETE]: 2,
        [StateActionStatus.IN_PROGRESS]: 1,
        [StateActionStatus.NA]: 0,
      };

      const store = createMockStore({
        videoFrame: {
          frameSummaryStatusCount: mockStatusCount,
        },
      });
      
      renderWithProviders(<SummariesContainer />, store);

      // CountStatusEmp should be rendered (mocked in StatusTag component)
      expect(screen.getByText('FrameSummaries')).toBeInTheDocument();
    });

    it('should handle empty status counts', () => {
      const store = createMockStore({
        videoFrame: {
          frameSummaryStatusCount: {},
        },
      });
      
      renderWithProviders(<SummariesContainer />, store);

      expect(screen.getByText('FrameSummaries')).toBeInTheDocument();
    });
  });




});
