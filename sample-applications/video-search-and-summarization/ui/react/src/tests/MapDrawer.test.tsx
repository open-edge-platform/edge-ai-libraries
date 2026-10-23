// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, screen } from '@testing-library/react';
import { Provider } from 'react-redux';
import { describe, expect, it, vi } from 'vitest';
import MapDrawer from '../components/MapView/MapDrawer';
import { GeoState } from '../redux/geo/geo';
import { SearchActions } from '../redux/search/searchSlice';
import { createSearchQuery, createSearchResult, createSearchState, createTestStore } from './testUtils';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const geo: GeoState = {
  source: 'geo-api',
  stale: false,
  loaded: true,
  intersections: {
    intersection_1: { label: 'Main St', lat: 37.51358, lon: -122.25591, cameras: {} },
    intersection_2: { label: 'Broadway', lat: 37.5391, lon: -122.30871, cameras: {} },
  },
};

const results = [
  createSearchResult({ id: 'r1', metadata: { video_id: 'v1', tags: 'intersection_1-camera2', relevance_score: 0.9 } }),
  createSearchResult({ id: 'r2', metadata: { video_id: 'v2', tags: 'intersection_1-camera4', relevance_score: 0.5 } }),
  createSearchResult({ id: 'r3', metadata: { video_id: 'v3', tags: 'camera1', relevance_score: 0.4 } }),
];

const renderDrawer = (open: boolean) => {
  const store = createTestStore({
    search: createSearchState({
      searchQueries: [createSearchQuery({ queryId: 'q1', results, topK: results.length })],
      selectedQuery: 'q1',
    }),
    geo: { ...geo, mapDrawerOpen: open },
  });
  render(
    <Provider store={store}>
      <MapDrawer />
    </Provider>,
  );
  return store;
};

describe('MapDrawer', () => {
  it('does not mount the map while closed', () => {
    renderDrawer(false);
    expect(screen.getByTestId('map-drawer')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.queryByTestId('map-view')).toBeNull();
  });

  it('pins the selected query results on their intersections and lists unmapped tags', () => {
    renderDrawer(true);

    expect(screen.getByTestId('map-view')).toBeInTheDocument();
    expect(screen.getByTestId('unmapped-notice')).toHaveTextContent('UnmappedTags');
  });

  it('closes from the close button and with Escape', () => {
    const store = renderDrawer(true);

    fireEvent.click(screen.getByRole('button', { name: 'CloseMap' }));
    expect(store.getState().geo.mapDrawerOpen).toBe(false);

    const reopened = renderDrawer(true);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(reopened.getState().geo.mapDrawerOpen).toBe(false);
  });

  it('moves focus to the close button when opened', () => {
    renderDrawer(true);
    expect(screen.getByRole('button', { name: 'CloseMap' })).toHaveFocus();
  });

  it('adds a pin when a watched query refresh brings a clip from a new intersection', () => {
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 800,
      height: 600,
      top: 0,
      left: 0,
      right: 800,
      bottom: 600,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect);
    const store = renderDrawer(true);
    expect(screen.queryByTestId('intersection-card-intersection_2')).toBeNull();

    // Same topK, so the new clip displaces the lowest-ranked result as a real refresh would.
    const refreshed = [
      results[0],
      createSearchResult({
        id: 'r4',
        metadata: { video_id: 'v4', tags: 'intersection_2-camera1', relevance_score: 0.7 },
      }),
      results[1],
    ];
    act(() => {
      store.dispatch(SearchActions.updateSearchQuery(createSearchQuery({ queryId: 'q1', results: refreshed })));
    });

    expect(screen.getByTestId('intersection-card-intersection_1')).toBeInTheDocument();
    expect(screen.getByTestId('intersection-card-intersection_2')).toBeInTheDocument();
    vi.restoreAllMocks();
  });
});
