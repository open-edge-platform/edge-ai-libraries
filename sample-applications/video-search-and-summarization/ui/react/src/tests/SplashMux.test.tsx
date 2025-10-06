// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { SplashSummarySearch } from '../components/MainPage/SplashMux';
import { UISlice, initialState as uiInitialState } from '../redux/ui/ui.slice';
import { MuxFeatures } from '../redux/ui/ui.model';

// Mock the sub-components to focus on SplashMux logic
vi.mock('../components/Summaries/SummaryContainer', () => ({
  default: () => <div data-testid="summary-container">Summary Container</div>
}));

vi.mock('../components/Search/SearchContainer', () => ({
  default: () => <div data-testid="search-container">Search Container</div>
}));

const createTestStore = (selectedMux = MuxFeatures.SUMMARY) => {
  return configureStore({
    reducer: {
      ui: UISlice.reducer,
    },
    preloadedState: {
      ui: {
        ...uiInitialState,
        selectedMux,
        promptEditing: null, // Can be null according to the interface
      },
    },
  });
};

const renderWithStore = (store = createTestStore()) => {
  return render(
    <Provider store={store}>
      <SplashSummarySearch />
    </Provider>
  );
};

describe('SplashMux Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render both Summary and Search buttons', () => {
    renderWithStore();
    
    expect(screen.getByLabelText('Summary')).toBeInTheDocument();
    expect(screen.getByLabelText('Search')).toBeInTheDocument();
  });

  it('should render Summary button as primary when SUMMARY is selected', () => {
    renderWithStore(createTestStore(MuxFeatures.SUMMARY));
    
    const summaryButton = screen.getByLabelText('Summary');
    const searchButton = screen.getByLabelText('Search');
    
    // Summary button should have primary style
    expect(summaryButton.closest('.cds--btn')).toHaveClass('cds--btn--primary');
    // Search button should have ghost style
    expect(searchButton.closest('.cds--btn')).toHaveClass('cds--btn--ghost');
  });

  it('should render Search button as primary when SEARCH is selected', () => {
    renderWithStore(createTestStore(MuxFeatures.SEARCH));
    
    const summaryButton = screen.getByLabelText('Summary');
    const searchButton = screen.getByLabelText('Search');
    
    // Search button should have primary style
    expect(searchButton.closest('.cds--btn')).toHaveClass('cds--btn--primary');
    // Summary button should have ghost style
    expect(summaryButton.closest('.cds--btn')).toHaveClass('cds--btn--ghost');
  });

  it('should display SummaryMainContainer when SUMMARY is selected', () => {
    renderWithStore(createTestStore(MuxFeatures.SUMMARY));
    
    expect(screen.getByTestId('summary-container')).toBeInTheDocument();
    expect(screen.queryByTestId('search-container')).not.toBeInTheDocument();
  });

  it('should display SearchMainContainer when SEARCH is selected', () => {
    renderWithStore(createTestStore(MuxFeatures.SEARCH));
    
    expect(screen.getByTestId('search-container')).toBeInTheDocument();
    expect(screen.queryByTestId('summary-container')).not.toBeInTheDocument();
  });

  it('should dispatch setMux action when Summary button is clicked', () => {
    const store = createTestStore(MuxFeatures.SEARCH); // Start with search selected
    
    renderWithStore(store);
    
    const summaryButton = screen.getByLabelText('Summary');
    fireEvent.click(summaryButton);
    
    // Check that the state has changed to SUMMARY
    const state = store.getState() as { ui: { selectedMux: MuxFeatures } };
    expect(state.ui.selectedMux).toBe(MuxFeatures.SUMMARY);
  });

  it('should dispatch setMux action when Search button is clicked', () => {
    const store = createTestStore(MuxFeatures.SUMMARY); // Start with summary selected
    
    renderWithStore(store);
    
    const searchButton = screen.getByLabelText('Search');
    fireEvent.click(searchButton);
    
    // Check that the state has changed to SEARCH
    const state = store.getState() as { ui: { selectedMux: MuxFeatures } };
    expect(state.ui.selectedMux).toBe(MuxFeatures.SEARCH);
  });

  it('should render SuperSidebar with correct styling', () => {
    const { container } = renderWithStore();
    
    // Find any div element that contains the buttons (the SuperSidebar)
    const sidebar = container.querySelector('div');
    expect(sidebar).toBeInTheDocument();
    
    // Ensure it contains both buttons
    const buttons = container.querySelectorAll('button');
    expect(buttons).toHaveLength(2);
  });

  it('should render Sigma icon in Summary button', () => {
    renderWithStore();
    
    const summaryButton = screen.getByLabelText('Summary');
    const sigmaIcon = summaryButton.querySelector('svg');
    expect(sigmaIcon).toBeInTheDocument();
  });

  it('should render DataAnalytics icon in Search button', () => {
    renderWithStore();
    
    const searchButton = screen.getByLabelText('Search');
    const analyticsIcon = searchButton.querySelector('svg');
    expect(analyticsIcon).toBeInTheDocument();
  });

  it('should toggle between containers when buttons are clicked multiple times', () => {
    const store = createTestStore(MuxFeatures.SUMMARY);
    renderWithStore(store);
    
    // Initially shows summary
    expect(screen.getByTestId('summary-container')).toBeInTheDocument();
    expect(screen.queryByTestId('search-container')).not.toBeInTheDocument();
    
    // Click search button
    const searchButton = screen.getByLabelText('Search');
    fireEvent.click(searchButton);
    
    // Should now show search
    expect(screen.getByTestId('search-container')).toBeInTheDocument();
    expect(screen.queryByTestId('summary-container')).not.toBeInTheDocument();
    
    // Click summary button
    const summaryButton = screen.getByLabelText('Summary');
    fireEvent.click(summaryButton);
    
    // Should now show summary again
    expect(screen.getByTestId('summary-container')).toBeInTheDocument();
    expect(screen.queryByTestId('search-container')).not.toBeInTheDocument();
  });

  it('should handle component rendering without errors', () => {
    expect(() => {
      renderWithStore();
    }).not.toThrow();
  });

  it('should have proper button alignment and labeling', () => {
    renderWithStore();
    
    const summaryButton = screen.getByLabelText('Summary');
    const searchButton = screen.getByLabelText('Search');
    
    // Both buttons should be icon buttons with proper alignment
    expect(summaryButton).toHaveAttribute('type', 'button');
    expect(searchButton).toHaveAttribute('type', 'button');
  });
});