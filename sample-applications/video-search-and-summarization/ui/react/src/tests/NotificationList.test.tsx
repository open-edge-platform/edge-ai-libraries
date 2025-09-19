// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { useDispatch, useSelector } from 'react-redux';

import NotificationList from '../components/Notification/NotificationList.tsx';
import { removeNotification } from '../redux/notification/notificationSlice.ts';
import { NotificationProps } from '../components/Notification/NotificationProps.ts';
import { NotificationSeverity } from '../components/Notification/notify.ts';

vi.mock('react-redux', () => ({
  useDispatch: vi.fn(),
  useSelector: vi.fn(),
}));

describe('NotificationList Component test suite', () => {
  const mockDispatch = vi.fn();

  beforeEach(() => {
    vi.mocked(useDispatch).mockReturnValue(mockDispatch);
  });

  const renderComponent = (notifications: NotificationProps[] = []) => {
    vi.mocked(useSelector).mockReturnValue(notifications);
    return render(<NotificationList />);
  };

  it('should render the component correctly with no notifications', () => {
    renderComponent();
    expect(
      screen.queryByTestId('notification-container'),
    ).toBeEmptyDOMElement();
  });

  it('should render the component correctly with notifications', () => {
    const notifications: NotificationProps[] = [
      {
        id: '1',
        kind: NotificationSeverity.INFO,
        title: 'Test Notification 1',
      },
      {
        id: '2',
        kind: NotificationSeverity.INFO,
        title: 'Test Notification 2',
      },
    ];
    renderComponent(notifications);

    expect(screen.getByTestId('notification-item-1')).toBeInTheDocument();
    expect(screen.getByTestId('notification-item-2')).toBeInTheDocument();
  });

  it('should remove a notification after the specified timeout', async () => {
    const notifications: NotificationProps[] = [
      {
        id: '1',
        kind: NotificationSeverity.INFO,
        title: 'Test Notification 1',
        timeout: 500,
      },
    ];
    renderComponent(notifications);

    await waitFor(
      () => {
        expect(mockDispatch).toHaveBeenCalledWith(removeNotification('1'));
      },
      { timeout: 1000 },
    );
  });

  it('should remove a notification when the close button is clicked', () => {
    const notifications: NotificationProps[] = [
      {
        id: '1',
        kind: NotificationSeverity.INFO,
        title: 'Test Notification 1',
      },
    ];
    renderComponent(notifications);

    const closeButton = screen.getByRole('button');
    fireEvent.click(closeButton);

    expect(mockDispatch).toHaveBeenCalledWith(removeNotification('1'));
  });

  it('should render INFO notification correctly', () => {
    const notifications: NotificationProps[] = [
      {
        id: '1',
        kind: NotificationSeverity.INFO,
        title: 'Info Notification',
      },
    ];
    renderComponent(notifications);

    expect(screen.getByTestId('notification-item-1')).toBeInTheDocument();
  });

  it('should render SUCCESS notification correctly', () => {
    const notifications: NotificationProps[] = [
      {
        id: '1',
        kind: NotificationSeverity.SUCCESS,
        title: 'Success Notification',
      },
    ];
    renderComponent(notifications);

    expect(screen.getByTestId('notification-item-1')).toBeInTheDocument();
  });

  it('should render WARNING notification correctly', () => {
    const notifications: NotificationProps[] = [
      {
        id: '1',
        kind: NotificationSeverity.WARNING,
        title: 'Warning Notification',
      },
    ];
    renderComponent(notifications);

    expect(screen.getByTestId('notification-item-1')).toBeInTheDocument();
  });

  it('should render ERROR notification correctly', () => {
    const notifications: NotificationProps[] = [
      {
        id: '1',
        kind: NotificationSeverity.ERROR,
        title: 'Error Notification',
      },
    ];
    renderComponent(notifications);

    expect(screen.getByTestId('notification-item-1')).toBeInTheDocument();
  });
});
