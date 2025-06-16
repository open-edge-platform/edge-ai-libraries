import store from '../../redux/store.ts';
import { addNotification } from '../../redux/notification/notificationSlice.ts';

export enum NotificationSeverity {
  SUCCESS = 'success',
  ERROR = 'error',
  WARNING = 'warning',
  INFO = 'info',
}

export const notify = (
  title: string,
  kind: NotificationSeverity,
  timeout: number = 3000,
): void => {
  store.dispatch(
    addNotification({
      title,
      kind,
      timeout,
    }),
  );
};
