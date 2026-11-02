// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';

import TimeFilterControl, {
  TimeFilterControlProps,
} from '../components/Search/TimeFilterControl';
import i18n from '../utils/i18n';

describe('TimeFilterControl Component test suite', () => {
  const renderComponent = (props: Partial<TimeFilterControlProps> = {}) => {
    const defaultProps: TimeFilterControlProps = {
      timeFilter: null,
      onChange: vi.fn(),
    };

    return render(
      <I18nextProvider i18n={i18n}>
        <TimeFilterControl {...defaultProps} {...props} />
      </I18nextProvider>,
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render the group heading as a fieldset legend', () => {
    const { container } = renderComponent();

    const legend = container.querySelector('legend');
    expect(legend).toBeInTheDocument();
    expect(legend).toHaveTextContent('Date added');
  });

  it('should describe an unset filter as having no time limit', () => {
    renderComponent();

    expect(screen.getByText('No time limit. Every video is searched.')).toBeInTheDocument();
  });

  it('should describe an active filter in terms of when videos were added', () => {
    renderComponent({ timeFilter: { value: 2, unit: 'weeks' } });

    expect(
      screen.getByText('Only videos added in the last 2 weeks are searched.'),
    ).toBeInTheDocument();
  });

  it('should use a singular unit for a value of one', () => {
    renderComponent({ timeFilter: { value: 1, unit: 'days' } });

    expect(
      screen.getByText('Only videos added in the last 1 day are searched.'),
    ).toBeInTheDocument();
  });

  it('should fall back to the first unit when the stored unit is unknown', () => {
    renderComponent({ timeFilter: { value: 3, unit: 'fortnights' as never } });

    expect(
      screen.getByText('Only videos added in the last 3 minutes are searched.'),
    ).toBeInTheDocument();
  });

  it('should keep the summary visually subordinate to the heading', () => {
    const { container } = renderComponent({ timeFilter: { value: 3, unit: 'days' } });

    const legend = container.querySelector('legend') as HTMLElement;
    const summary = screen.getByText('Only videos added in the last 3 days are searched.');

    // The heading must not share the summary's size/weight, otherwise it reads
    // as another sentence rather than a label.
    expect(legend.style.fontSize).toBe('0.875rem');
    expect(legend.style.fontWeight).toBe('600');
    expect(summary).toHaveStyle({ fontSize: '0.75rem', fontWeight: '400' });
  });

  it('should disable the unit dropdown while the value is zero', () => {
    renderComponent({ timeFilter: { value: 0, unit: 'weeks' } });

    expect(screen.getByRole('combobox')).toBeDisabled();
  });

  it('should enable the unit dropdown once a value is set', () => {
    renderComponent({ timeFilter: { value: 5, unit: 'weeks' } });

    expect(screen.getByRole('combobox')).not.toBeDisabled();
  });

  it('should not render a visible "Unit" field label', () => {
    renderComponent({ timeFilter: { value: 5, unit: 'weeks' } });

    // "Unit" is retained for assistive tech only; on screen the selected value
    // already reads as the unit.
    const visibleUnitLabel = screen
      .queryAllByText('Unit')
      .find((node) => !node.className.includes('visually-hidden'));
    expect(visibleUnitLabel).toBeUndefined();
  });

  it('should default the tooltip to opening downwards', () => {
    const { container } = renderComponent();

    expect(container.querySelector('legend .cds--tooltip')).toHaveClass('cds--popover--bottom-start');
  });

  it('should open the tooltip upwards when asked, so it is not clipped', () => {
    const { container } = renderComponent({ tooltipAlign: 'top-start' });

    expect(container.querySelector('legend .cds--tooltip')).toHaveClass('cds--popover--top-start');
  });

  it('should report value changes to the parent', () => {
    const onChange = vi.fn();
    renderComponent({ timeFilter: { value: 2, unit: 'weeks' }, onChange });

    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '7' } });

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ value: 7, unit: 'weeks' }),
    );
  });
});
