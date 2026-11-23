// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import axios from 'axios';
import { ReactElement } from 'react';

import { IntervalDisplay, QuerySettings } from '../components/Search/SearchContent';
import { SearchReducers } from '../redux/search/searchSlice';
import { SearchQueryStatus, SearchQueryUI } from '../redux/search/search';
import i18n from '../utils/i18n';

vi.mock('axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock('../config', async () => ({
  ...(await vi.importActual<object>('../config')),
  APP_URL: 'http://localhost:3000',
}));

const query = (overrides: Partial<SearchQueryUI> = {}): SearchQueryUI => ({
  queryId: 'q1',
  query: 'red car',
  watch: false,
  results: [],
  tags: [],
  queryStatus: SearchQueryStatus.IDLE,
  createdAt: '2026-01-01',
  updatedAt: '2026-01-01',
  topK: 4,
  minPeakScore: 0,
  ...overrides,
});

const renderWith = (ui: ReactElement, q: SearchQueryUI) => {
  const store = configureStore({
    reducer: { search: SearchReducers },
    preloadedState: {
      search: {
        searchQueries: [q],
        selectedQuery: q.queryId,
        suggestedTags: [],
        unreads: [],
        triggerLoad: false,
        searchConfig: { minPeakScoreDefault: 0 },
      },
    },
  });
  render(
    <Provider store={store}>
      <I18nextProvider i18n={i18n}>{ui}</I18nextProvider>
    </Provider>,
  );
  return store;
};

describe('Minimum peak score on a saved query', () => {
  beforeEach(() => {
    vi.mocked(axios.post).mockResolvedValue({ data: query({ minPeakScore: 0.3 }) });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('re-runs the query only when a typed value is confirmed', async () => {
    renderWith(<QuerySettings />, query({ minPeakScore: 0.2 }));

    const input = screen.getByLabelText('Minimum peak score value');
    fireEvent.change(input, { target: { value: '0.25' } });
    fireEvent.change(input, { target: { value: '0.3' } });

    expect(axios.post).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post).toHaveBeenCalledWith('http://localhost:3000/search/q1/refetch', {
      minPeakScore: 0.3,
    });
  });

  it('re-runs the query once the slider is released, not while it moves', async () => {
    renderWith(<QuerySettings />, query({ minPeakScore: 0.2 }));

    const slider = screen.getByRole('slider', { name: 'Minimum peak score slider' });
    fireEvent.keyDown(slider, { key: 'ArrowRight' });
    fireEvent.keyDown(slider, { key: 'ArrowRight' });

    expect(axios.post).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.keyUp(slider, { key: 'ArrowRight' });
    });

    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post).toHaveBeenCalledWith('http://localhost:3000/search/q1/refetch', {
      minPeakScore: 0.202,
    });
  });

  it('re-runs the query right away when the filter is switched on', async () => {
    renderWith(<QuerySettings />, query());

    await act(async () => {
      fireEvent.click(screen.getByRole('switch'));
    });

    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post).toHaveBeenCalledWith('http://localhost:3000/search/q1/refetch', {
      minPeakScore: 0.2,
    });
  });

  it('shows the active threshold next to the query', () => {
    renderWith(<IntervalDisplay />, query({ minPeakScore: 0.25 }));

    expect(screen.getByText('Min peak score: 0.25')).toBeInTheDocument();
  });

  it('shows nothing when the filter is off', () => {
    renderWith(<IntervalDisplay />, query());

    expect(screen.queryByText(/Min peak score/)).not.toBeInTheDocument();
  });
});

describe('Date added on a saved query', () => {
  beforeEach(() => {
    vi.mocked(axios.post).mockResolvedValue({ data: query() });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('re-runs the query only when the typed value is confirmed', async () => {
    renderWith(<QuerySettings />, query({ timeFilter: { value: 2, unit: 'hours' } }));

    const input = screen.getByRole('spinbutton', { name: 'Time value' });
    fireEvent.change(input, { target: { value: '1' } });
    fireEvent.change(input, { target: { value: '12' } });

    expect(axios.post).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post).toHaveBeenCalledWith(
      'http://localhost:3000/search/q1/refetch',
      expect.objectContaining({ timeFilter: expect.objectContaining({ value: 12, unit: 'hours' }) }),
    );
  });
});
