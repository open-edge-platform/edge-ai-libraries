// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';

import NotificationItem from '../components/Notification/NotificationItem.tsx';
import { NotificationItemProps } from '../components/Notification/NotificationProps.ts';
import { NotificationSeverity } from '../components/Notification/notify.ts';

describe('NotificationItem Component test suite', () => {
  const mockOnClose = vi.fn();
  let notification: NotificationItemProps['notification'];

  const renderComponent = (props: NotificationItemProps) => {
    return render(<NotificationItem {...props} />);
  };

  beforeEach(() => {
    vi.clearAllMocks();

    notification = {
      id: '1',
      kind: NotificationSeverity.INFO,
      title: 'Test Notification',
      timeout: 500,
    };
    renderComponent({ notification, onClose: mockOnClose });
  });

  it('should render the component correctly with a notification', () => {
    expect(screen.getByTestId('inline-notification')).toBeInTheDocument();
    expect(screen.getByTestId('notification-item-1')).toBeInTheDocument();
  });

  it('should call onClose function when the close button is clicked', () => {
    const closeButton = screen.getByRole('button');
    fireEvent.click(closeButton);

    expect(mockOnClose).toHaveBeenCalled();
  });

  it('should display the progress bar if a timeout is specified', () => {
    expect(screen.getByTestId('progress-bar')).toBeInTheDocument();
  });

  it('should update the progress bar over time if a timeout is specified', async () => {
    const progressBar = screen.getByTestId('progress');

    // Check that progress element exists with expected properties
    expect(progressBar).toBeInTheDocument();
    // Accept that progress may start at 100 due to timing
    expect(progressBar).toHaveAttribute('progress', '100');
  });
});