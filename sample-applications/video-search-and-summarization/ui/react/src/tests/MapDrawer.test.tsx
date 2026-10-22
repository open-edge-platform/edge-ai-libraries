// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from '@testing-library/react';
import { Provider } from 'react-redux';
import { describe, expect, it, vi } from 'vitest';
import MapDrawer from '../components/MapView/MapDrawer';
import { GeoState } from '../redux/geo/geo';
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
});
