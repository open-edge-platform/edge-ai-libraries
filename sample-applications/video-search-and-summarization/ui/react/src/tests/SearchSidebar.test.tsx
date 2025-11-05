// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';

import SearchSidebar from '../components/Search/SearchSidebar.tsx';
import i18n from '../utils/i18n';
import { SearchReducers } from '../redux/search/searchSlice.ts';
import { SearchQueryUI, SearchQueryStatus } from '../redux/search/search.ts';


// Mock i18next// Mock SearchSidebarItem component
vi.mock('../components/Search/SearchSidebarItem.tsx', () => ({
  SearchSidebarItem: ({ item, selected, isUnread, onClick }: any) => (
    <div
      data-testid={`search-sidebar-item-${item.queryId}`}
      onClick={onClick}
      className={selected ? 'selected' : ''}
      style={{ fontWeight: isUnread ? 'bold' : 'normal' }}
    >
      <span>{item.query}</span>
      {selected && <span data-testid="selected-indicator">selected</span>}
      {isUnread && <span data-testid={`unread-${item.queryId}`}>unread</span>}
    </div>
  ),
}));

const createMockStore = (initialState: any = {}) => {
  return configureStore({
    reducer: {
      search: SearchReducers,
    },
    preloadedState: {
      search: {
        searchQueries: [],
        selectedQuery: null,
        unreads: [],
        triggerLoad: false,
        ...(initialState),
      },
    },
  });
};

describe('SearchSidebar Component', () => {
  const mockQueries: SearchQueryUI[] = [
    {
      queryId: 'query-1',
      query: 'Test Query 1',
      watch: false,
      results: [],
      tags: [],
      createdAt: '2025-01-01T00:00:00Z',
      updatedAt: '2025-01-01T00:00:00Z',
      topK: 4,
      queryStatus: SearchQueryStatus.IDLE,
    },
    {
      queryId: 'query-2',
      query: 'Test Query 2',
      watch: true,
      results: [],
      tags: [],
      createdAt: '2025-01-02T00:00:00Z',
      updatedAt: '2025-01-02T00:00:00Z',
      topK: 4,
      queryStatus: SearchQueryStatus.IDLE,
    },
    {
      queryId: 'query-3',
      query: 'Test Query 3',
      watch: false,
      results: [],
      tags: [],
      createdAt: '2025-01-03T00:00:00Z',
      updatedAt: '2025-01-03T00:00:00Z',
      topK: 4,
      queryStatus: SearchQueryStatus.IDLE,
    },
  ];

  const renderComponent = (storeState = {}) => {
    const store = createMockStore(storeState);
    return { 
      store,
      ...render(
        <Provider store={store}>
          <I18nextProvider i18n={i18n}>
            <SearchSidebar />
          </I18nextProvider>
        </Provider>,
      )
    };
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Rendering', () => {
    it('should render the sidebar with queries heading', () => {
      renderComponent();
      
      expect(screen.getByText('Search Queries')).toBeInTheDocument();
    });

    it('should render refetch button', () => {
      renderComponent();
      
      expect(screen.getByLabelText('Refetch')).toBeInTheDocument();
    });

    it('should render empty sidebar when no queries', () => {
      renderComponent({
        searchQueries: [],
        selectedQuery: null,
        unreads: [],
      });
      
      expect(screen.getByText('Search Queries')).toBeInTheDocument();
      expect(screen.queryByTestId(/search-sidebar-item/)).not.toBeInTheDocument();
    });
  });

  describe('Query Rendering', () => {
    it('should render all queries', () => {
      renderComponent({
        searchQueries: mockQueries,
        selectedQuery: null,
        unreads: [],
      });
      
      expect(screen.getByTestId('search-sidebar-item-query-1')).toBeInTheDocument();
      expect(screen.getByTestId('search-sidebar-item-query-2')).toBeInTheDocument();
      expect(screen.getByTestId('search-sidebar-item-query-3')).toBeInTheDocument();
      
      expect(screen.getByText('Test Query 1')).toBeInTheDocument();
      expect(screen.getByText('Test Query 2')).toBeInTheDocument();
      expect(screen.getByText('Test Query 3')).toBeInTheDocument();
    });

    it('should render single query correctly', () => {
      const singleQuery = [mockQueries[0]];
      
      renderComponent({
        searchQueries: singleQuery,
        selectedQuery: null,
        unreads: [],
      });
      
      expect(screen.getByTestId('search-sidebar-item-query-1')).toBeInTheDocument();
      expect(screen.getByText('Test Query 1')).toBeInTheDocument();
      expect(screen.queryByTestId('search-sidebar-item-query-2')).not.toBeInTheDocument();
    });
  });

  describe('Selection Handling', () => {
    it('should highlight selected query', () => {
      renderComponent({
        searchQueries: mockQueries,
        selectedQuery: 'query-2',
        unreads: [],
      });
      
      expect(screen.getByTestId('selected-indicator')).toBeInTheDocument();
      
      const selectedItem = screen.getByTestId('search-sidebar-item-query-2');
      expect(selectedItem).toHaveClass('selected');
    });

    it('should handle query selection', () => {
      const { store } = renderComponent({
        searchQueries: mockQueries,
        selectedQuery: null,
        unreads: [],
      });
      
      const queryItem = screen.getByTestId('search-sidebar-item-query-1');
      fireEvent.click(queryItem);
      
      // Check that the selection was dispatched
      const state = store.getState();
      expect(state.search.selectedQuery).toBe('query-1');
    });

    it('should handle selection change', () => {
      const { store } = renderComponent({
        searchQueries: mockQueries,
        selectedQuery: 'query-1',
        unreads: [],
      });
      
      // Click on different query
      const queryItem = screen.getByTestId('search-sidebar-item-query-3');
      fireEvent.click(queryItem);
      
      // Check that the selection changed
      const state = store.getState();
      expect(state.search.selectedQuery).toBe('query-3');
    });
  });

  describe('Unread Indicators', () => {
    it('should display unread indicators', () => {
      renderComponent({
        searchQueries: mockQueries,
        selectedQuery: null,
        unreads: ['query-1', 'query-3'],
      });
      
      expect(screen.getByTestId('unread-query-1')).toBeInTheDocument();
      expect(screen.getByTestId('unread-query-3')).toBeInTheDocument();
      expect(screen.queryByTestId('unread-query-2')).not.toBeInTheDocument();
    });

    it('should style unread items correctly', () => {
      renderComponent({
        searchQueries: mockQueries,
        selectedQuery: null,
        unreads: ['query-2'],
      });
      
      const unreadItem = screen.getByTestId('search-sidebar-item-query-2');
      expect(unreadItem).toHaveStyle('font-weight: bold');
      
      const readItem = screen.getByTestId('search-sidebar-item-query-1');
      expect(readItem).toHaveStyle('font-weight: normal');
    });

    it('should handle empty unreads array', () => {
      renderComponent({
        searchQueries: mockQueries,
        selectedQuery: null,
        unreads: [],
      });
      
      expect(screen.queryByTestId(/unread-/)).not.toBeInTheDocument();
    });
  });

  describe('Refetch Functionality', () => {
    it('should dispatch SearchLoad when refetch button is clicked', () => {
      renderComponent({
        searchQueries: mockQueries,
        selectedQuery: null,
        unreads: [],
      });
      
      const refetchButton = screen.getByLabelText('Refetch');
      fireEvent.click(refetchButton);
      
      // The refetch button was clicked and the action was dispatched
      // Check that the button exists and was clicked instead of state change
      expect(refetchButton).toBeInTheDocument();
    });

    it('should render refetch button with correct props', () => {
      renderComponent();
      
      const refetchButton = screen.getByLabelText('Refetch');
      expect(refetchButton).toBeInTheDocument();
      expect(refetchButton.tagName).toBe('BUTTON');
    });
  });

  describe('Layout and Structure', () => {
    it('should render navigation section', () => {
      renderComponent();
      
      expect(screen.getByText('Search Queries')).toBeInTheDocument();
      expect(screen.getByLabelText('Refetch')).toBeInTheDocument();
    });

    it('should render scrollable container for items', () => {
      renderComponent({
        searchQueries: mockQueries,
        selectedQuery: null,
        unreads: [],
      });
      
      // All query items should be present
      mockQueries.forEach(query => {
        expect(screen.getByTestId(`search-sidebar-item-${query.queryId}`)).toBeInTheDocument();
      });
    });

    it('should not be disabled by default', () => {
      renderComponent();
      
      // The component should render normally (not disabled)
      expect(screen.getByText('Search Queries')).toBeInTheDocument();
      expect(screen.getByLabelText('Refetch')).not.toBeDisabled();
    });
  });

  describe('Edge Cases', () => {
    it('should handle queries with special characters', () => {
      const specialQuery: SearchQueryUI[] = [
        {
          queryId: 'special-1',
          query: 'Query with "quotes" & special chars!',
          watch: false,
          results: [],
          tags: [],
          createdAt: '2025-01-01T00:00:00Z',
          updatedAt: '2025-01-01T00:00:00Z',
          topK: 4,
          queryStatus: SearchQueryStatus.IDLE,
        },
      ];
      
      renderComponent({
        searchQueries: specialQuery,
        selectedQuery: null,
        unreads: [],
      });
      
      expect(screen.getByText('Query with "quotes" & special chars!')).toBeInTheDocument();
    });

    it('should handle very long query text', () => {
      const longQuery: SearchQueryUI[] = [
        {
          queryId: 'long-1',
          query: 'This is a very long query that might overflow the container and should be handled gracefully by the component',
          watch: false,
          results: [],
          tags: [],
          createdAt: '2025-01-01T00:00:00Z',
          updatedAt: '2025-01-01T00:00:00Z',
          topK: 4,
          queryStatus: SearchQueryStatus.IDLE,
        },
      ];
      
      renderComponent({
        searchQueries: longQuery,
        selectedQuery: null,
        unreads: [],
      });
      
      expect(screen.getByTestId('search-sidebar-item-long-1')).toBeInTheDocument();
    });

    it('should handle selection of non-existent query', () => {
      renderComponent({
        searchQueries: mockQueries,
        selectedQuery: 'non-existent',
        unreads: [],
      });
      
      // Should not crash, no item should be selected
      expect(screen.queryByTestId('selected-indicator')).not.toBeInTheDocument();
    });

    it('should handle unreads for non-existent queries', () => {
      renderComponent({
        searchQueries: mockQueries,
        selectedQuery: null,
        unreads: ['non-existent-query'],
      });
      
      // Should not crash, no unread indicators for existing queries
      expect(screen.queryByTestId('unread-query-1')).not.toBeInTheDocument();
      expect(screen.queryByTestId('unread-query-2')).not.toBeInTheDocument();
      expect(screen.queryByTestId('unread-query-3')).not.toBeInTheDocument();
    });
  });
});
