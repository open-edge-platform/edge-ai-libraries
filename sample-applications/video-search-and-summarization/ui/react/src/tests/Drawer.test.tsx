// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';

import Drawer from '../components/Drawer/Drawer.tsx';
import i18n from '../utils/i18n';

vi.mock('../components/Navigation/Navigation.tsx', () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid='navigation'>{children}</div>
  ),
}));

describe('Drawer Component test suite', () => {
  const mockClose = vi.fn();

  const renderComponent = (
    isOpen = false,
    title = '',
    children: React.ReactNode = null,
  ) =>
    render(
      <I18nextProvider i18n={i18n}>
        <Drawer isOpen={isOpen} close={mockClose} title={title}>
          {children}
        </Drawer>
      </I18nextProvider>,
    );

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render the component correctly when closed', () => {
    renderComponent(false);

    const drawerWrapper = screen.getByTestId('drawer-wrapper');
    expect(drawerWrapper).toHaveStyle('transform: translateX(100%)');
  });

  it('should render the component correctly when open', () => {
    renderComponent(true);

    const drawerWrapper = screen.getByTestId('drawer-wrapper');
    expect(drawerWrapper).toHaveStyle('transform: translateX(0)');
  });

  it('should render the title correctly', () => {
    const title = 'Test Title';
    renderComponent(true, title);
    expect(screen.getByText(title)).toBeInTheDocument();
  });

  it('should render the default title when no title is provided', () => {
    renderComponent(true);
    expect(
      screen.getByText(new RegExp(i18n.t('drawerTitle'), 'i')),
    ).toBeInTheDocument();
  });

  it('should render children correctly', () => {
    const children = <div data-testid='child'>Child Content</div>;
    renderComponent(true, '', children);

    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('should call close function when close button is clicked', () => {
    renderComponent(true);

    const closeButton = screen.getByTestId('close-drawer-button');
    fireEvent.click(closeButton);
    expect(mockClose).toHaveBeenCalled();
  });

  it('should call close function when overlay is clicked', () => {
    renderComponent(true);

    const overlay = screen.getByTestId('overlay');
    fireEvent.click(overlay);
    expect(mockClose).toHaveBeenCalled();
  });
});
