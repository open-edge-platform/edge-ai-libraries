// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';

import Navbar from '../components/Navbar/Navbar.tsx';
import i18n from '../utils/i18n';

describe('Navbar Component test suite', () => {
  const renderComponent = () =>
    render(
      <I18nextProvider i18n={i18n}>
        <Navbar />
      </I18nextProvider>,
    );

  beforeEach(() => renderComponent());

  it('should render the component correctly', () => {
    const navbarElement = screen.getByTestId('navbar');
    expect(navbarElement).toBeInTheDocument();
  });
});
