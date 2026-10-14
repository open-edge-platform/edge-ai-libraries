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
import { SearchReducers } from '../redux/search/searchSlice.ts';
import { SearchQueryUI, SearchQueryStatus, SearchRefreshConfig } from '../redux/search/search.ts';

vi.mock('../config', () => ({
  APP_URL: 'http://localhost:3000',
  ASSETS_ENDPOINT: 'http://localhost:3000/assets',
  FEATURE_SEARCH: 'ON',
  FEATURE_SUMMARY: 'ON',
  FEATURE_STATE: { ON: 'ON', OFF: 'OFF' },
}));

const makeQuery = (overrides: Partial<SearchQueryUI> = {}): SearchQueryUI => ({
  queryId: 'query-watched',
  query: 'brown jacket',
  watch: true,
  results: [],
  tags: [],
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
  topK: 4,
  queryStatus: SearchQueryStatus.IDLE,
  ...overrides,
});

const makeRefreshConfig = (overrides: Partial<SearchRefreshConfig> = {}): SearchRefreshConfig => ({
  enabled: true,
  intervalMs: 10000,
  quietPeriodMs: 3000,
  batchSize: 10,
  minQueryIntervalMs: 10000,
  maxQueriesPerTick: 50,
  ...overrides,
});

const renderSidebar = (initialState: Partial<Record<string, unknown>> = {}) => {
  const store = configureStore({
    reducer: { search: SearchReducers },
    preloadedState: {
      search: {
        searchQueries: [],
        selectedQuery: null,
        unreads: [],
        triggerLoad: false,
        suggestedTags: [],
        refreshConfig: makeRefreshConfig(),
        ...initialState,
      },
    },
  });

  render(
    <Provider store={store}>
      <I18nextProvider i18n={i18n}>
        <SearchSidebar />
      </I18nextProvider>
    </Provider>,
  );
};

describe('SearchSidebarItem layout', () => {
  it('renders the query text and its refresh metadata', () => {
    renderSidebar({ searchQueries: [makeQuery()] });

    expect(screen.getByText('brown jacket')).toBeInTheDocument();
    expect(screen.getByText('Not refreshed yet')).toBeInTheDocument();
  });

  // Regression guard: the metadata used to sit next to the query text in the
  // same flex row. Because it is nowrap and the text container has
  // overflow: hidden, a narrow sidebar collapsed the query text to zero width
  // and only the timestamp stayed visible. Stacking them keeps the query text
  // readable at any width.
  it('stacks the query text and metadata in one flexible container', () => {
    renderSidebar({ searchQueries: [makeQuery()] });

    const text = screen.getByText('brown jacket');
    const meta = screen.getByText('Not refreshed yet');

    expect(text.parentElement).toBe(meta.parentElement);
    expect(text.parentElement).toHaveClass('query-body');
  });

  it('keeps the full query readable via a title attribute when truncated', () => {
    renderSidebar({ searchQueries: [makeQuery({ query: 'a very long search query that will be clipped' })] });

    expect(screen.getByText('a very long search query that will be clipped')).toHaveAttribute(
      'title',
      'a very long search query that will be clipped',
    );
  });

  it('shows the last updated time when the query has been refreshed', () => {
    renderSidebar({
      searchQueries: [makeQuery({ lastRefreshedAt: '2026-01-01T10:30:00Z' })],
    });

    expect(screen.getByText(/^Updated /)).toBeInTheDocument();
  });

  it('does not render refresh metadata for an unwatched query', () => {
    renderSidebar({ searchQueries: [makeQuery({ watch: false })] });

    expect(screen.getByText('brown jacket')).toBeInTheDocument();
    expect(screen.queryByText('Not refreshed yet')).not.toBeInTheDocument();
  });

  it('hides refresh metadata while the query is running so the spinner owns the row', () => {
    renderSidebar({
      searchQueries: [makeQuery({ queryStatus: SearchQueryStatus.RUNNING })],
    });

    expect(screen.getByTestId('search-running-query-watched')).toBeInTheDocument();
    expect(screen.queryByText('Not refreshed yet')).not.toBeInTheDocument();
  });

  it('hides refresh metadata when auto refresh is disabled on the deployment', () => {
    renderSidebar({
      searchQueries: [makeQuery()],
      refreshConfig: makeRefreshConfig({ enabled: false }),
    });

    expect(screen.queryByText('Not refreshed yet')).not.toBeInTheDocument();
  });
});
