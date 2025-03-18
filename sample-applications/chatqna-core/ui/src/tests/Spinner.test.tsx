// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import '@testing-library/jest-dom';

import Spinner from '../components/Spinner/Spinner.tsx';

describe('Spinner Component test suite', () => {
  const renderComponent = (size?: number) => render(<Spinner size={size} />);

  it('should render the component correctly', () => {
    renderComponent();

    const spinnerContainer = screen.getByTestId('spinner-container');
    expect(spinnerContainer).toBeInTheDocument();
  });

  it('should apply the default size correctly', () => {
    renderComponent();

    const spinnerContainer = screen.getByTestId('spinner-container');
    expect(spinnerContainer).toHaveStyle({ width: '50px', height: '50px' });
  });

  it('should apply a custom size correctly', () => {
    renderComponent(100);

    const spinnerContainer = screen.getByTestId('spinner-container');
    expect(spinnerContainer).toHaveStyle({ width: '100px', height: '100px' });
  });

  it('should render the correct number of bars', () => {
    renderComponent();

    const bars = screen.getAllByTestId('spinner-bar');
    expect(bars.length).toBe(5);
  });

  it('should apply the correct animation properties to each bar', () => {
    renderComponent();

    const bars = screen.getAllByTestId('spinner-bar');
    const delays = ['-1.2s', '-1.1s', '-1s', '-0.9s', '-0.8s'];

    bars.forEach((bar, index) => {
      expect(bar).toHaveStyle({ animationDelay: delays[index] });
    });
  });
});
