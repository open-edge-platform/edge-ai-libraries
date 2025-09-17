import { render, screen, fireEvent } from '@testing-library/react';
import { Provider } from 'react-redux';
import { I18nextProvider } from 'react-i18next';
import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom';
import { configureStore } from '@reduxjs/toolkit';
import SummarySideBar from '../components/Summaries/SummarySideBar';
import { SummarySlice } from '../redux/summary/summarySlice';
import { VideoChunkSlice } from '../redux/summary/videoChunkSlice';
import { VideoFrameSlice } from '../redux/summary/videoFrameSlice';
import { VideoSlice } from '../redux/video/videoSlice';
import i18n from '../utils/i18n';

// Mock child components
vi.mock('../components/Summaries/SummarySideBarItem', () => ({
  default: ({ item, onClick }: any) => (
    <div 
      data-testid="sidebar-item" 
      data-state-id={item.stateId}
      onClick={() => onClick(item)}
    >
      {item.title || 'Untitled Summary'}
    </div>
  ),
}));

// Mock react-i18next
vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
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

const mockSidebarSummaries = [
  {
    stateId: 'summary-1',
    title: 'First Summary',
    selected: false,
  },
  {
    stateId: 'summary-2', 
    title: 'Second Summary',
    selected: true,
  },
  {
    stateId: 'summary-3',
    title: 'Third Summary', 
    selected: false,
  },
];

describe('SummarySidebar Component', () => {
    const renderComponent = (summaryData: any[] = []) => {
    const summariesObject = summaryData.reduce((acc, summary) => {
      acc[summary.stateId] = summary;
      return acc;
    }, {});

    const storeWithData = createMockStore({
      summaries: {
        selectedSummary: summaryData.length > 0 ? summaryData[0].stateId : null,
        summaries: summariesObject,
        sidebarSummaries: summaryData,
      },
    });

    return render(
      <Provider store={storeWithData}>
        <I18nextProvider i18n={i18n}>
          <SummarySideBar />
        </I18nextProvider>
      </Provider>
    );
  };

  describe('Basic Rendering', () => {
    it('should render sidebar container', () => {
      renderComponent([]);
      expect(screen.getByRole('complementary')).toBeInTheDocument();
    });

    it('should render navigation header', () => {
      renderComponent([]);
      expect(screen.getByText('Summaries')).toBeInTheDocument();
    });

    it('should handle empty summaries list', () => {
      renderComponent([]);
      expect(screen.queryByTestId('sidebar-item')).not.toBeInTheDocument();
    });
  });

  describe('Sidebar Items Rendering', () => {
    it('should render all sidebar summaries', () => {
      renderComponent(mockSidebarSummaries);
      
      const sidebarItems = screen.getAllByTestId('sidebar-item');
      expect(sidebarItems).toHaveLength(mockSidebarSummaries.length);
    });

    it('should render summaries with correct titles', () => {
      renderComponent(mockSidebarSummaries);
      
      expect(screen.getByText('First Summary')).toBeInTheDocument();
      expect(screen.getByText('Second Summary')).toBeInTheDocument();
      expect(screen.getByText('Third Summary')).toBeInTheDocument();
    });

    it('should handle summaries without titles', () => {
      const summariesWithoutTitles = [
        { stateId: 'no-title-1', title: '', selected: false },
        { stateId: 'no-title-2', title: null, selected: false },
      ];
      
      expect(() => renderComponent(summariesWithoutTitles)).not.toThrow();
    });
  });

  describe('Click Interactions', () => {
    it('should handle summary item clicks', () => {
      renderComponent(mockSidebarSummaries);
      
      const firstItem = screen.getByText('First Summary');
      fireEvent.click(firstItem);
      
      // Should not throw error when clicked
      expect(firstItem).toBeInTheDocument();
    });
  });

  describe('Integration Tests', () => {
    it('should integrate with Redux store correctly', () => {
      renderComponent(mockSidebarSummaries);
      
      expect(screen.getByText('Summaries')).toBeInTheDocument();
      expect(screen.getAllByTestId('sidebar-item')).toHaveLength(3);
    });

    it('should work with i18n provider', () => {
      renderComponent([]);
      
      expect(screen.getByText('Summaries')).toBeInTheDocument();
    });
  });
});
