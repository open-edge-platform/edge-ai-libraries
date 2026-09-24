// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';

import SearchSidebar from '../components/Search/SearchSidebar.tsx';
import i18n from '../utils/i18n';
import { SearchActions, SearchReducers, SearchSelector } from '../redux/search/searchSlice.ts';
import { SearchQueryUI, SearchQueryStatus, SearchResult } from '../redux/search/search.ts';

vi.mock('../config', () => ({
  APP_URL: 'http://localhost:3000',
  ASSETS_ENDPOINT: 'http://localhost:3000/assets',
  FEATURE_SEARCH: 'ON',
  FEATURE_SUMMARY: 'ON',
  FEATURE_STATE: { ON: 'ON', OFF: 'OFF' },
}));

const makeResult = (videoId: string, timestamp: number): SearchResult =>
  ({
    metadata: { video_id: videoId, timestamp, relevance_score: 0.5 },
  }) as unknown as SearchResult;

const makeQuery = (overrides: Partial<SearchQueryUI> = {}): SearchQueryUI => ({
  queryId: 'query-running',
  query: 'a running query',
  watch: false,
  results: [],
  tags: [],
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
  topK: 4,
  queryStatus: SearchQueryStatus.RUNNING,
  ...overrides,
});

const makeStore = (initialState: Partial<Record<string, unknown>> = {}) =>
  configureStore({
    reducer: { search: SearchReducers },
    preloadedState: {
      search: {
        searchQueries: [],
        selectedQuery: null,
        unreads: [],
        triggerLoad: false,
        suggestedTags: [],
        ...initialState,
      },
    },
  });

const renderSidebar = (initialState: Partial<Record<string, unknown>> = {}) => {
  const store = makeStore(initialState);
  render(
    <Provider store={store}>
      <I18nextProvider i18n={i18n}>
        <SearchSidebar />
      </I18nextProvider>
    </Provider>,
  );
  return store;
};

describe('Search in-progress query handling', () => {
  describe('SearchSidebar listing', () => {
    it('lists a running query that has no results yet', () => {
      renderSidebar({ searchQueries: [makeQuery()], selectedQuery: 'query-running' });

      expect(screen.getByText('a running query')).toBeInTheDocument();
    });

    it('shows a running indicator on the in-progress item', () => {
      renderSidebar({ searchQueries: [makeQuery()], selectedQuery: 'query-running' });

      expect(screen.getByTestId('search-running-query-running')).toBeInTheDocument();
    });

    it('does not show a running indicator on an idle query', () => {
      renderSidebar({
        searchQueries: [makeQuery({ queryStatus: SearchQueryStatus.IDLE })],
      });

      expect(screen.queryByTestId('search-running-query-running')).not.toBeInTheDocument();
    });

    it('lists an errored query so it can be seen and deleted', () => {
      renderSidebar({
        searchQueries: [
          makeQuery({ queryId: 'query-error', query: 'broken query', queryStatus: SearchQueryStatus.ERROR }),
        ],
      });

      expect(screen.getByText('broken query')).toBeInTheDocument();
    });

    it('lists a completed query that returned zero results', () => {
      renderSidebar({
        searchQueries: [
          makeQuery({ queryId: 'query-empty', query: 'no hits', queryStatus: SearchQueryStatus.IDLE, results: [] }),
        ],
      });

      expect(screen.getByText('no hits')).toBeInTheDocument();
    });

    it('still renders the in-progress banner', () => {
      renderSidebar({ searchQueries: [makeQuery()], selectedQuery: 'query-running' });

      expect(screen.getByText('(1) search in progress')).toBeInTheDocument();
    });
  });

  describe('SearchSelector loading flags', () => {
    it('reports initial loading for a running query with no results', () => {
      const store = makeStore({ searchQueries: [makeQuery()], selectedQuery: 'query-running' });
      const selected = SearchSelector(store.getState() as never);

      expect(selected.isSelectedInitialLoading).toBe(true);
      expect(selected.isSelectedRefreshing).toBe(false);
      expect(selected.isSelectedInProgress).toBe(true);
    });

    it('reports refreshing (not initial loading) for a running query that already has results', () => {
      const store = makeStore({
        searchQueries: [makeQuery({ results: [makeResult('vid-a', 10)] })],
        selectedQuery: 'query-running',
      });
      const selected = SearchSelector(store.getState() as never);

      expect(selected.isSelectedInitialLoading).toBe(false);
      expect(selected.isSelectedRefreshing).toBe(true);
      // Existing results must remain available so the view is not torn down mid-refresh.
      expect(selected.selectedResults).toHaveLength(1);
    });

    it('reports neither flag for an idle query', () => {
      const store = makeStore({
        searchQueries: [makeQuery({ queryStatus: SearchQueryStatus.IDLE, results: [makeResult('vid-a', 10)] })],
        selectedQuery: 'query-running',
      });
      const selected = SearchSelector(store.getState() as never);

      expect(selected.isSelectedInitialLoading).toBe(false);
      expect(selected.isSelectedRefreshing).toBe(false);
    });
  });

  describe('updateSearchQuery churn control', () => {
    it('keeps the query at its original position when it updates', () => {
      const store = makeStore({
        searchQueries: [
          makeQuery({ queryId: 'a', query: 'first', queryStatus: SearchQueryStatus.IDLE }),
          makeQuery({ queryId: 'b', query: 'second', queryStatus: SearchQueryStatus.IDLE }),
          makeQuery({ queryId: 'c', query: 'third', queryStatus: SearchQueryStatus.IDLE }),
        ],
      });

      store.dispatch(
        SearchActions.updateSearchQuery({
          queryId: 'a',
          query: 'first',
          results: [makeResult('vid-a', 1)],
          queryStatus: SearchQueryStatus.RUNNING,
        }),
      );

      const ids = store.getState().search.searchQueries.map((query: SearchQueryUI) => query.queryId);
      expect(ids).toEqual(['a', 'b', 'c']);
    });

    it('does not mark the currently selected query as unread', () => {
      const store = makeStore({
        searchQueries: [makeQuery({ queryId: 'a', queryStatus: SearchQueryStatus.IDLE })],
        selectedQuery: 'a',
      });

      store.dispatch(
        SearchActions.updateSearchQuery({ queryId: 'a', results: [makeResult('vid-a', 1)] }),
      );

      expect(store.getState().search.unreads).not.toContain('a');
    });

    it('marks a non-selected query as unread exactly once across repeated updates', () => {
      const store = makeStore({
        searchQueries: [
          makeQuery({ queryId: 'a', queryStatus: SearchQueryStatus.IDLE }),
          makeQuery({ queryId: 'b', queryStatus: SearchQueryStatus.IDLE }),
        ],
        selectedQuery: 'a',
      });

      store.dispatch(SearchActions.updateSearchQuery({ queryId: 'b', results: [makeResult('vid-b', 1)] }));
      store.dispatch(SearchActions.updateSearchQuery({ queryId: 'b', results: [makeResult('vid-b', 2)] }));
      store.dispatch(SearchActions.updateSearchQuery({ queryId: 'b', results: [makeResult('vid-b', 3)] }));

      const unreads = store.getState().search.unreads.filter((id: string) => id === 'b');
      expect(unreads).toHaveLength(1);
    });
  });
});
