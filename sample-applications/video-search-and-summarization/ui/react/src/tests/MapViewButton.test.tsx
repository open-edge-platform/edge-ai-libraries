// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from '@testing-library/react';
import { Provider } from 'react-redux';
import { describe, expect, it, vi } from 'vitest';
import { QueryInfo } from '../components/Search/SearchContent';
import { createSearchQuery, createSearchState, createTestStore } from './testUtils';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const renderQueryInfo = (withIntersections: boolean) => {
  const store = createTestStore({
    search: createSearchState({
      searchQueries: [createSearchQuery({ queryId: 'query-1', query: 'vehicles' })],
      selectedQuery: 'query-1',
    }),
    geo: {
      intersections: withIntersections ? { intersection_1: { label: 'Main St', lat: 0, lon: 0, cameras: {} } } : {},
      source: withIntersections ? 'fallback' : 'none',
      loaded: true,
    },
  });
  render(
    <Provider store={store}>
      <QueryInfo />
    </Provider>,
  );
  return store;
};

describe('Map View button', () => {
  it('is hidden when no locations are known', () => {
    renderQueryInfo(false);
    expect(screen.queryByRole('button', { name: 'MapView' })).toBeNull();
    expect(screen.getByRole('button', { name: 'GroupByTag' })).toBeInTheDocument();
  });

  it('sits before Group by Tag and toggles the map drawer without touching grouping', () => {
    const store = renderQueryInfo(true);
    const mapButton = screen.getByRole('button', { name: 'MapView' });
    const groupButton = screen.getByRole('button', { name: 'GroupByTag' });

    expect(mapButton.compareDocumentPosition(groupButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(mapButton).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(mapButton);
    expect(store.getState().geo.mapDrawerOpen).toBe(true);
    expect(store.getState().search.searchQueries[0].showVideoGroups).toBeFalsy();

    fireEvent.click(mapButton);
    expect(store.getState().geo.mapDrawerOpen).toBe(false);
  });
});
