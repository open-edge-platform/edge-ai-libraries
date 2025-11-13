// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { Provider } from 'react-redux';
import { I18nextProvider } from 'react-i18next';
// Removed BrowserRouter import since it's not available in the project
import { configureStore } from '@reduxjs/toolkit';
import { SplashAtomic, SplashAtomicSearch, SplashAtomicSummary } from '../components/MainPage/SplashAtomic';
import i18n from '../utils/i18n';
import { SummaryReducers } from '../redux/summary/summarySlice';
import { SearchReducers } from '../redux/search/searchSlice';
import { UIReducer } from '../redux/ui/ui.slice';
import { VideoReducers } from '../redux/video/videoSlice';
import notificationReducer from '../redux/notification/notificationSlice';
import { VideoChunkReducer } from '../redux/summary/videoChunkSlice';
import { VideoFrameReducer } from '../redux/summary/videoFrameSlice';

// Mock the child components to avoid complex rendering issues
vi.mock('../components/Search/SearchContainer', () => ({
  default: () => <div data-testid="search-main-container">Search Container</div>
}));

vi.mock('../components/Summaries/SummaryContainer', () => ({
  default: () => <div data-testid="summary-main-container">Summary Container</div>
}));

// Create a mock store for testing
const createMockStore = () => {
  return configureStore({
    reducer: {
      summaries: SummaryReducers,
      search: SearchReducers,
      ui: UIReducer,
      videos: VideoReducers,
      notifications: notificationReducer,
      videoChunks: VideoChunkReducer,
      videoFrames: VideoFrameReducer,
    },
  });
};

// Test wrapper component
const TestWrapper = ({ children }: { children: React.ReactNode }) => {
  const store = createMockStore();
  return (
    <Provider store={store}>
      <I18nextProvider i18n={i18n}>
        {children}
      </I18nextProvider>
    </Provider>
  );
};

describe('SplashAtomic Component', () => {
  describe('SplashAtomic', () => {
    it('should render basic splash atomic component', () => {
      render(
        <TestWrapper>
          <SplashAtomic />
        </TestWrapper>
      );

      expect(screen.getByText('SOMETING')).toBeInTheDocument();
      expect(screen.getByRole('heading', { level: 3 })).toBeInTheDocument();
    });

    it('should render with proper component structure', () => {
      const { container } = render(
        <TestWrapper>
          <SplashAtomic />
        </TestWrapper>
      );

      const heading = container.querySelector('h3');
      expect(heading).toBeInTheDocument();
      expect(heading?.textContent).toBe('SOMETING');
    });
  });

  describe('SplashAtomicSearch', () => {
    it('should render search container component', () => {
      render(
        <TestWrapper>
          <SplashAtomicSearch />
        </TestWrapper>
      );

      expect(screen.getByTestId('search-main-container')).toBeInTheDocument();
      expect(screen.getByText('Search Container')).toBeInTheDocument();
    });

    it('should render without any additional elements besides search container', () => {
      const { container } = render(
        <TestWrapper>
          <SplashAtomicSearch />
        </TestWrapper>
      );

      const searchContainer = screen.getByTestId('search-main-container');
      expect(searchContainer).toBeInTheDocument();
      expect(container.children).toHaveLength(1);
    });
  });

  describe('SplashAtomicSummary', () => {
    it('should render summary container component', () => {
      render(
        <TestWrapper>
          <SplashAtomicSummary />
        </TestWrapper>
      );

      expect(screen.getByTestId('summary-main-container')).toBeInTheDocument();
      expect(screen.getByText('Summary Container')).toBeInTheDocument();
    });

    it('should render summary container within fragment wrapper', () => {
      const { container } = render(
        <TestWrapper>
          <SplashAtomicSummary />
        </TestWrapper>
      );

      const summaryContainer = screen.getByTestId('summary-main-container');
      expect(summaryContainer).toBeInTheDocument();
      expect(container.children).toHaveLength(1);
    });

    it('should have proper component integration', () => {
      render(
        <TestWrapper>
          <SplashAtomicSummary />
        </TestWrapper>
      );

      // Verify that the summary container is rendered and accessible
      const summaryElement = screen.getByTestId('summary-main-container');
      expect(summaryElement).toBeVisible();
    });
  });

  describe('Component Export Validation', () => {
    it('should export all three components as named exports', () => {
      expect(SplashAtomic).toBeDefined();
      expect(SplashAtomicSearch).toBeDefined();
      expect(SplashAtomicSummary).toBeDefined();
    });

    it('should all be functional components', () => {
      expect(typeof SplashAtomic).toBe('function');
      expect(typeof SplashAtomicSearch).toBe('function');
      expect(typeof SplashAtomicSummary).toBe('function');
    });
  });
});