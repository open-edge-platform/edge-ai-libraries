// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';

import MinPeakScoreControl, {
  MinPeakScoreControlProps,
  minPeakScoreOnValue,
} from '../components/Search/MinPeakScoreControl';
import i18n from '../utils/i18n';

describe('MinPeakScoreControl', () => {
  const renderControl = (props: Partial<MinPeakScoreControlProps> = {}) => {
    const onChange = vi.fn();
    render(
      <I18nextProvider i18n={i18n}>
        <MinPeakScoreControl value={0} onChange={onChange} {...props} />
      </I18nextProvider>,
    );
    return {
      onChange,
      toggle: screen.getByRole('switch'),
      slider: screen.getByRole('slider'),
      input: screen.getByLabelText('Minimum peak score value') as HTMLInputElement,
      apply: screen.getByTestId('min-peak-score-apply'),
    };
  };

  it('starts off with the slider and text box disabled when the value is 0', () => {
    const { toggle, slider, input } = renderControl();

    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(slider.closest('.cds--slider')).toHaveClass('cds--slider--disabled');
    expect(input).toBeDisabled();
    expect(screen.getByText('No score limit. All matches are returned.')).toBeInTheDocument();
  });

  it('moves to 0.2 when switched on and to 0 when switched off', () => {
    const { toggle, slider, input, onChange } = renderControl();

    fireEvent.click(toggle);
    expect(onChange).toHaveBeenLastCalledWith(0.2);
    expect(slider).toHaveAttribute('aria-valuenow', '0.2');
    expect(input.value).toBe('0.2');
    expect(input).not.toBeDisabled();

    fireEvent.click(toggle);
    expect(onChange).toHaveBeenLastCalledWith(0);
    expect(input).toBeDisabled();
  });

  it('starts on at a non-zero value', () => {
    const { toggle, input } = renderControl({ value: 0.35 });

    expect(toggle).toHaveAttribute('aria-checked', 'true');
    expect(input.value).toBe('0.35');
  });

  it('moves the slider while typing but applies only on Enter', () => {
    const { slider, input, apply, onChange } = renderControl({ value: 0.2 });

    expect(apply).toHaveAttribute('data-state', 'applied');
    fireEvent.change(input, { target: { value: '0.125' } });

    expect(slider).toHaveAttribute('aria-valuenow', '0.125');
    expect(onChange).not.toHaveBeenCalled();
    expect(apply).toHaveAttribute('data-state', 'pending');
    expect(apply).toHaveAccessibleName('Apply minimum peak score (Enter)');
    expect(screen.queryByText('Enter a number from 0 to 1 with up to 3 decimals.')).not.toBeInTheDocument();

    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenLastCalledWith(0.125);
    expect(apply).toHaveAttribute('data-state', 'applied');
    expect(apply).toHaveAccessibleName('Minimum peak score applied');
  });

  it('applies a typed value when the text box loses focus', () => {
    const { input, onChange } = renderControl({ value: 0.2 });

    fireEvent.change(input, { target: { value: '0.3' } });
    fireEvent.blur(input);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenLastCalledWith(0.3);
  });

  it('applies a typed value from the apply icon', () => {
    const { input, apply, onChange } = renderControl({ value: 0.2 });

    fireEvent.change(input, { target: { value: '0.45' } });
    fireEvent.click(apply);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenLastCalledWith(0.45);
  });

  it('does not re-apply an unchanged value', () => {
    const { input, onChange } = renderControl({ value: 0.2 });

    fireEvent.change(input, { target: { value: '0.200' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.blur(input);

    expect(onChange).not.toHaveBeenCalled();
  });

  it.each(['1.5', '0.1234', 'abc', '-0.1'])('rejects %s and reverts it on blur', (bad) => {
    const { slider, input, onChange } = renderControl({ value: 0.2 });

    fireEvent.change(input, { target: { value: bad } });

    expect(onChange).not.toHaveBeenCalled();
    expect(slider).toHaveAttribute('aria-valuenow', '0.2');
    expect(screen.getByText('Enter a number from 0 to 1 with up to 3 decimals.')).toBeInTheDocument();

    fireEvent.blur(input);
    expect(input.value).toBe('0.2');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('does not flag a value that is still being typed', () => {
    const { input, onChange } = renderControl({ value: 0.2 });

    fireEvent.change(input, { target: { value: '0.' } });

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByText('Enter a number from 0 to 1 with up to 3 decimals.')).not.toBeInTheDocument();
  });

  it('updates the text box while the slider moves and applies on key release', () => {
    const { slider, input, apply, onChange } = renderControl({ value: 0.2 });

    fireEvent.keyDown(slider, { key: 'ArrowRight' });
    fireEvent.keyDown(slider, { key: 'ArrowRight' });

    expect(input.value).toBe('0.202');
    expect(onChange).not.toHaveBeenCalled();
    expect(apply).toHaveAttribute('data-state', 'pending');

    fireEvent.keyUp(slider, { key: 'ArrowRight' });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenLastCalledWith(0.202);
    expect(apply).toHaveAttribute('data-state', 'applied');
  });

  it('applies the slider value once the pointer is released', () => {
    const { slider, onChange } = renderControl({ value: 0.2 });

    fireEvent.keyDown(slider, { key: 'ArrowRight' });
    fireEvent.mouseDown(slider);
    expect(onChange).not.toHaveBeenCalled();

    fireEvent.mouseUp(document);

    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('switches on at the deployment default when one is set', () => {
    expect(minPeakScoreOnValue(0)).toBe(0.2);
    expect(minPeakScoreOnValue(undefined)).toBe(0.2);
    expect(minPeakScoreOnValue(0.4)).toBe(0.4);

    const { toggle, onChange } = renderControl({ onValue: 0.4 });
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenLastCalledWith(0.4);
  });
});
