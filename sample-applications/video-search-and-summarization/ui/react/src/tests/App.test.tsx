// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import App from '../App.tsx';

vi.mock('../components/MainPage/MainPage.tsx', () => ({
  default: () => <div data-testid='main-page'>MainPage Component</div>,
}));

vi.mock('../components/UserInfoModal/UserInfoModal.tsx', () => ({
  default: () => <div data-testid='user-info'>UserInfoModal Component</div>,
}));

vi.mock('../components/Notification/NotificationList.tsx', () => ({
  default: () => (
    <div data-testid='notification-list'>NotificationList Component</div>
  ),
}));

describe('App Component test suite', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    render(<App />);
  });

  it('should render MainPage component', () => {
    expect(screen.getByTestId('main-page')).toBeInTheDocument();
  });

  it('should render NotificationList component', () => {
    expect(screen.getByTestId('notification-list')).toBeInTheDocument();
  });
});
