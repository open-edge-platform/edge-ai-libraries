// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';

import SearchOutputCountControl, { SEARCH_OUTPUT_COUNT_MAX } from '../components/Search/SearchOutputCountControl';
import i18n from '../utils/i18n';

describe('SearchOutputCountControl', () => {
  const renderControl = (value = 4) => {
    const onChange = vi.fn();
    render(
      <I18nextProvider i18n={i18n}>
        <SearchOutputCountControl value={value} onChange={onChange} />
      </I18nextProvider>,
    );
    return { onChange, slider: screen.getByRole('slider', { name: 'Search output count slider' }) };
  };

  it('renders the heading with an info button', () => {
    renderControl();

    expect(screen.getByText('Search output count')).toBeInTheDocument();
    // Carbon's Tooltip names the trigger by its tooltip text.
    expect(screen.getByRole('button', { name: /How many of the ranked results to show/ })).toHaveAttribute(
      'aria-label',
      'About the search output count',
    );
  });

  it('always shows the current value in the bubble and the summary', () => {
    const { slider } = renderControl(7);

    expect(slider).toHaveAttribute('aria-valuenow', '7');
    expect(slider).toHaveAttribute('aria-valuemin', '1');
    expect(slider).toHaveAttribute('aria-valuemax', String(SEARCH_OUTPUT_COUNT_MAX));
    expect(screen.getByTestId('search-output-count-slider-bubble')).toHaveTextContent('7');
    expect(screen.getByText('Showing the top 7 results.')).toBeInTheDocument();
  });

  it('uses the singular summary for one result', () => {
    renderControl(1);

    expect(screen.getByText('Showing the top result.')).toBeInTheDocument();
  });

  it('reports a new value when the slider moves', () => {
    const { slider, onChange } = renderControl(4);

    fireEvent.keyDown(slider, { key: 'ArrowRight', which: 39 });

    expect(onChange).toHaveBeenLastCalledWith(5);
  });
});
