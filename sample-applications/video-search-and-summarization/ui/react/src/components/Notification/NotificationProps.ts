// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { NotificationSeverity } from './notify.ts';

export interface NotificationProps {
  id: string;
  title: string;
  kind: NotificationSeverity;
  timeout?: number;
}

export interface NotificationContextType {
  notify: (notification: Omit<NotificationProps, 'id'>) => void;
  removeNotification: (id: string) => void;
}

export interface NotificationItemProps {
  notification: NotificationProps;
  onClose: () => void;
}
