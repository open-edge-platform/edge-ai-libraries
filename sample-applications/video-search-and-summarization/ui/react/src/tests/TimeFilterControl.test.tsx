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

    // The summary is helper text below the controls, not part of the heading,
    // otherwise it reads as another sentence of the label. (styled-components is
    // mocked in tests, so the heading/helper type styles are not visible here.)
    expect(legend).toHaveTextContent(/^Date added/);
    expect(legend).not.toContainElement(summary);
    expect(summary.tagName).toBe('P');
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

  const setup = (props: Partial<TimeFilterControlProps> = {}) => {
    const onChange = vi.fn();
    renderComponent({ timeFilter: { value: 2, unit: 'weeks' }, onChange, ...props });
    return {
      onChange,
      input: screen.getByRole('spinbutton') as HTMLInputElement,
      apply: screen.getByTestId('time-filter-apply'),
    };
  };

  it('should not report a value while it is being typed', () => {
    const { input, apply, onChange } = setup();

    expect(apply).toHaveAttribute('data-state', 'applied');
    fireEvent.change(input, { target: { value: '1' } });
    fireEvent.change(input, { target: { value: '12' } });

    expect(onChange).not.toHaveBeenCalled();
    expect(input.value).toBe('12');
    expect(apply).toHaveAttribute('data-state', 'pending');
    expect(apply).toHaveAccessibleName('Apply date added filter (Enter)');
    // The summary keeps describing the applied filter until the draft is applied.
    expect(screen.getByText('Only videos added in the last 2 weeks are searched.')).toBeInTheDocument();
  });

  it('should report the value on Enter', () => {
    const { input, onChange } = setup();

    fireEvent.change(input, { target: { value: '7' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ value: 7, unit: 'weeks' }));
  });

  it('should report the value when the field loses focus', () => {
    const { input, onChange } = setup();

    fireEvent.change(input, { target: { value: '7' } });
    fireEvent.blur(input);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ value: 7, unit: 'weeks' }));
  });

  it('should report the value from the apply icon', () => {
    const { input, apply, onChange } = setup();

    fireEvent.change(input, { target: { value: '9' } });
    fireEvent.click(apply);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ value: 9, unit: 'weeks' }));
  });

  it('should treat the +/- steppers as editing, applied once the field is left', () => {
    const { input, onChange } = setup();

    const increment = screen.getByRole('button', { name: /increment/i });
    fireEvent.click(increment);
    fireEvent.click(increment);
    // Focus moving from the input to its own stepper is still editing.
    fireEvent.blur(input, { relatedTarget: increment });

    expect(onChange).not.toHaveBeenCalled();
    expect(input.value).toBe('4');

    fireEvent.blur(increment);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ value: 4, unit: 'weeks' }));
  });

  it('should clear the filter when an emptied field is applied', () => {
    const { input, onChange } = setup();

    fireEvent.change(input, { target: { value: '' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('should not report an unchanged value', () => {
    const { input, onChange } = setup();

    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.blur(input);

    expect(onChange).not.toHaveBeenCalled();
  });

  it('should flag an invalid value and revert it when the field is left', () => {
    const { input, onChange } = setup();

    fireEvent.change(input, { target: { value: '1.5' } });

    expect(screen.getByText('Enter a whole number, 0 or more.')).toBeInTheDocument();

    fireEvent.blur(input);

    expect(onChange).not.toHaveBeenCalled();
    expect(input.value).toBe('2');
  });

  it('should apply the typed number together with a newly picked unit', () => {
    // jsdom has no scrollIntoView, which Carbon's Dropdown calls when opening.
    Element.prototype.scrollIntoView ??= vi.fn();
    const { input, onChange } = setup();

    fireEvent.change(input, { target: { value: '5' } });
    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(screen.getByRole('option', { name: 'Days' }));

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ value: 5, unit: 'days' }));
  });
});
