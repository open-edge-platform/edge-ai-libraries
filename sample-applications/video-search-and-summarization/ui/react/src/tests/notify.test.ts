// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the store and addNotification action
vi.mock('../redux/store.ts', () => ({
  default: {
    dispatch: vi.fn()
  }
}));

vi.mock('../redux/notification/notificationSlice.ts', () => ({
  addNotification: vi.fn((payload) => payload)
}));

import { notify, NotificationSeverity } from '../components/Notification/notify';
import store from '../redux/store';
import { addNotification } from '../redux/notification/notificationSlice';

describe('notify utility test suite', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should dispatch notification with default timeout', () => {
    const title = 'Test notification';
    const kind = NotificationSeverity.INFO;
    
    notify(title, kind);
    
    expect(addNotification).toHaveBeenCalledWith({
      title,
      kind,
      timeout: 3000
    });
    expect(store.dispatch).toHaveBeenCalledWith({
      title,
      kind,
      timeout: 3000
    });
  });

  it('should dispatch notification with custom timeout', () => {
    const title = 'Custom timeout notification';
    const kind = NotificationSeverity.WARNING;
    const timeout = 5000;
    
    notify(title, kind, timeout);
    
    expect(addNotification).toHaveBeenCalledWith({
      title,
      kind,
      timeout
    });
    expect(store.dispatch).toHaveBeenCalledWith({
      title,
      kind,
      timeout
    });
  });

  it('should handle SUCCESS notification severity', () => {
    const title = 'Success message';
    const kind = NotificationSeverity.SUCCESS;
    
    notify(title, kind);
    
    expect(addNotification).toHaveBeenCalledWith({
      title,
      kind,
      timeout: 3000
    });
  });

  it('should handle ERROR notification severity', () => {
    const title = 'Error message';
    const kind = NotificationSeverity.ERROR;
    const timeout = 8000;
    
    notify(title, kind, timeout);
    
    expect(addNotification).toHaveBeenCalledWith({
      title,
      kind,
      timeout
    });
  });

  it('should handle WARNING notification severity', () => {
    const title = 'Warning message';
    const kind = NotificationSeverity.WARNING;
    
    notify(title, kind);
    
    expect(addNotification).toHaveBeenCalledWith({
      title,
      kind,
      timeout: 3000
    });
  });

  it('should handle INFO notification severity', () => {
    const title = 'Info message';
    const kind = NotificationSeverity.INFO;
    
    notify(title, kind);
    
    expect(addNotification).toHaveBeenCalledWith({
      title,
      kind,
      timeout: 3000
    });
  });

  it('should handle zero timeout', () => {
    const title = 'No timeout notification';
    const kind = NotificationSeverity.INFO;
    const timeout = 0;
    
    notify(title, kind, timeout);
    
    expect(addNotification).toHaveBeenCalledWith({
      title,
      kind,
      timeout: 0
    });
  });

  it('should handle empty string title', () => {
    const title = '';
    const kind = NotificationSeverity.ERROR;
    
    notify(title, kind);
    
    expect(addNotification).toHaveBeenCalledWith({
      title: '',
      kind,
      timeout: 3000
    });
  });

  it('should verify NotificationSeverity enum values', () => {
    expect(NotificationSeverity.SUCCESS).toBe('success');
    expect(NotificationSeverity.ERROR).toBe('error');
    expect(NotificationSeverity.WARNING).toBe('warning');
    expect(NotificationSeverity.INFO).toBe('info');
  });

  it('should work with negative timeout values', () => {
    const title = 'Negative timeout test';
    const kind = NotificationSeverity.WARNING;
    const timeout = -1000;
    
    notify(title, kind, timeout);
    
    expect(addNotification).toHaveBeenCalledWith({
      title,
      kind,
      timeout: -1000
    });
  });
});
