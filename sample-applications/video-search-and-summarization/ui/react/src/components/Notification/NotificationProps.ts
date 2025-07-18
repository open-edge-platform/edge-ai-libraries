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
