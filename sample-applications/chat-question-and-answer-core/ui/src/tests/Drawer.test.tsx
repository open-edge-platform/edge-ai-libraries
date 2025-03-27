// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { it, describe, expect, afterEach, vi } from 'vitest';
import { I18nextProvider } from 'react-i18next';

import i18n from '../utils/i18n';
import Drawer from '../components/Drawer/Drawer.tsx';
import { ReactNode } from 'react';

describe('Drawer Component test suite', () => {
  const closeMock = vi.fn();

  const renderComponent = (
    isOpen: boolean,
    title?: ReactNode,
    children?: ReactNode,
  ) => {
    return render(
      <I18nextProvider i18n={i18n}>
        <Drawer isOpen={isOpen} close={closeMock} title={title}>
          {children}
        </Drawer>
      </I18nextProvider>,
    );
  };

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should render the component correctly', () => {
    renderComponent(true, 'Test Title', <div>Test Content</div>);

    expect(screen.getByTestId('overlay')).toBeInTheDocument();
    expect(screen.getByTestId('drawer-wrapper')).toBeInTheDocument();
  });

  it('should render the component correctly when open', () => {
    renderComponent(true, 'Test Title', <div>Test Content</div>);

    expect(screen.getByText('Test Title')).toBeInTheDocument();
    expect(screen.getByText('Test Content')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /×/i })).toBeInTheDocument();
  });

  it('should call close function when close button is clicked', () => {
    renderComponent(true, 'Test Title', <div>Test Content</div>);

    const closeButton = screen.getByRole('button', { name: /×/i });
    fireEvent.click(closeButton);

    expect(closeMock).toHaveBeenCalledTimes(1);
  });

  it('should call close function when overlay is clicked', () => {
    renderComponent(true, 'Test Title', <div>Test Content</div>);

    const overlay = screen.getByTestId('overlay');
    fireEvent.click(overlay);

    expect(closeMock).toHaveBeenCalledTimes(1);
  });

  it('should display default title when no title is provided', () => {
    renderComponent(true, undefined, <div>Test Content</div>);

    expect(screen.getByText(i18n.t('drawerTitle'))).toBeInTheDocument();
  });
});
