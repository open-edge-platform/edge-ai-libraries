// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest';
import type { 
  NotificationProps, 
  NotificationContextType, 
  NotificationItemProps 
} from '../components/Notification/NotificationProps';
import { NotificationSeverity } from '../components/Notification/notify';

describe('NotificationProps Module', () => {
  describe('NotificationProps interface', () => {
    it('should define correct structure for NotificationProps', () => {
      const notification: NotificationProps = {
        id: 'test-id',
        title: 'Test notification',
        kind: NotificationSeverity.SUCCESS,
        timeout: 5000,
      };

      expect(notification.id).toBe('test-id');
      expect(notification.title).toBe('Test notification');
      expect(notification.kind).toBe(NotificationSeverity.SUCCESS);
      expect(notification.timeout).toBe(5000);
    });

    it('should allow optional timeout property', () => {
      const notificationWithoutTimeout: NotificationProps = {
        id: 'test-id-2',
        title: 'Test notification without timeout',
        kind: NotificationSeverity.INFO,
      };

      expect(notificationWithoutTimeout.id).toBe('test-id-2');
      expect(notificationWithoutTimeout.title).toBe('Test notification without timeout');
      expect(notificationWithoutTimeout.kind).toBe(NotificationSeverity.INFO);
      expect(notificationWithoutTimeout.timeout).toBeUndefined();
    });

    it('should work with all NotificationSeverity types', () => {
      const successNotification: NotificationProps = {
        id: '1',
        title: 'Success',
        kind: NotificationSeverity.SUCCESS,
      };

      const errorNotification: NotificationProps = {
        id: '2',
        title: 'Error',
        kind: NotificationSeverity.ERROR,
      };

      const warningNotification: NotificationProps = {
        id: '3',
        title: 'Warning',
        kind: NotificationSeverity.WARNING,
      };

      const infoNotification: NotificationProps = {
        id: '4',
        title: 'Info',
        kind: NotificationSeverity.INFO,
      };

      expect(successNotification.kind).toBe(NotificationSeverity.SUCCESS);
      expect(errorNotification.kind).toBe(NotificationSeverity.ERROR);
      expect(warningNotification.kind).toBe(NotificationSeverity.WARNING);
      expect(infoNotification.kind).toBe(NotificationSeverity.INFO);
    });
  });

  describe('NotificationContextType interface', () => {
    it('should define correct function signatures', () => {
      const mockNotify = (notification: Omit<NotificationProps, 'id'>) => {
        console.log(notification);
      };

      const mockRemoveNotification = (id: string) => {
        console.log(`Removing: ${id}`);
      };

      const context: NotificationContextType = {
        notify: mockNotify,
        removeNotification: mockRemoveNotification,
      };

      expect(typeof context.notify).toBe('function');
      expect(typeof context.removeNotification).toBe('function');
    });

    it('should allow notify function to accept notification without id', () => {
      const notificationData: Omit<NotificationProps, 'id'> = {
        title: 'Test',
        kind: NotificationSeverity.SUCCESS,
        timeout: 3000,
      };

      const mockContext: NotificationContextType = {
        notify: (notification) => {
          expect(notification.title).toBe('Test');
          expect(notification.kind).toBe(NotificationSeverity.SUCCESS);
          expect(notification.timeout).toBe(3000);
          expect((notification as any).id).toBeUndefined();
        },
        removeNotification: () => {},
      };

      mockContext.notify(notificationData);
    });
  });

  describe('NotificationItemProps interface', () => {
    it('should define correct structure', () => {
      const mockNotification: NotificationProps = {
        id: 'item-test',
        title: 'Item test notification',
        kind: NotificationSeverity.WARNING,
        timeout: 2000,
      };

      const mockOnClose = () => {
        console.log('Closing notification');
      };

      const itemProps: NotificationItemProps = {
        notification: mockNotification,
        onClose: mockOnClose,
      };

      expect(itemProps.notification).toBe(mockNotification);
      expect(typeof itemProps.onClose).toBe('function');
      expect(itemProps.notification.id).toBe('item-test');
      expect(itemProps.notification.title).toBe('Item test notification');
      expect(itemProps.notification.kind).toBe(NotificationSeverity.WARNING);
      expect(itemProps.notification.timeout).toBe(2000);
    });

    it('should work with notification without timeout', () => {
      const mockNotification: NotificationProps = {
        id: 'no-timeout-test',
        title: 'No timeout test',
        kind: NotificationSeverity.ERROR,
      };

      const itemProps: NotificationItemProps = {
        notification: mockNotification,
        onClose: () => {},
      };

      expect(itemProps.notification.timeout).toBeUndefined();
    });
  });

  describe('Type compatibility and edge cases', () => {
    it('should handle empty string values', () => {
      const notification: NotificationProps = {
        id: '',
        title: '',
        kind: NotificationSeverity.INFO,
      };

      expect(notification.id).toBe('');
      expect(notification.title).toBe('');
    });

    it('should handle zero timeout', () => {
      const notification: NotificationProps = {
        id: 'zero-timeout',
        title: 'Zero timeout test',
        kind: NotificationSeverity.SUCCESS,
        timeout: 0,
      };

      expect(notification.timeout).toBe(0);
    });

    it('should work with long strings', () => {
      const longTitle = 'This is a very long notification title that could potentially be used in the application to test if the interface handles long strings correctly';
      const longId = 'this-is-a-very-long-id-that-could-be-generated-by-some-uuid-library-or-other-mechanism';

      const notification: NotificationProps = {
        id: longId,
        title: longTitle,
        kind: NotificationSeverity.WARNING,
        timeout: 10000,
      };

      expect(notification.id.length).toBeGreaterThan(50);
      expect(notification.title.length).toBeGreaterThan(100);
    });

    it('should maintain type safety with NotificationSeverity enum', () => {
      // Test that only valid NotificationSeverity values are accepted
      const validNotification: NotificationProps = {
        id: 'valid',
        title: 'Valid notification',
        kind: NotificationSeverity.SUCCESS,
      };

      expect(Object.values(NotificationSeverity)).toContain(validNotification.kind);
    });
  });
});
