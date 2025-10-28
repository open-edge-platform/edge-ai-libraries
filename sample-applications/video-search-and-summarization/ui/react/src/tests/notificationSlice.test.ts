// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { vi, describe, beforeEach, it, expect, afterEach } from 'vitest';

import notificationReducer, {
  addNotification,
  removeNotification,
} from '../redux/notification/notificationSlice.ts';
import { NotificationProps } from '../components/Notification/NotificationProps.ts';
import { uuidv4 } from '../utils/util.ts';
import { NotificationSeverity } from '../components/Notification/notify.ts';

vi.mock('../utils/util.ts', () => ({
  uuidv4: vi.fn(),
}));

describe('notificationSlice test suite', () => {
  const initialState: NotificationProps[] = [];

  beforeEach(() => {
    vi.mocked(uuidv4).mockReturnValue('test-uuid');
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it('should return the initial state', () => {
    expect(notificationReducer(undefined, { type: 'unknown' })).toEqual(
      initialState,
    );
  });

  it('should handle addNotification', () => {
    const newNotification = {
      title: 'Test Title',
      kind: NotificationSeverity.INFO,
    };
    const actual = notificationReducer(
      initialState,
      addNotification(newNotification),
    );
    expect(actual.length).toBe(1);
    expect(actual[0]).toEqual({ ...newNotification, id: 'test-uuid' });
  });

  it('should handle removeNotification', () => {
    const stateWithNotification: NotificationProps[] = [
      {
        id: 'test-uuid',
        title: 'Test notification',
        kind: NotificationSeverity.INFO,
      },
    ];
    const actual = notificationReducer(
      stateWithNotification,
      removeNotification('test-uuid'),
    );
    expect(actual.length).toBe(0);
  });
});
