// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { useEffect, type FC } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import styled from 'styled-components';

import { NotificationProps } from './NotificationProps.ts';
import { removeNotification } from '../../redux/notification/notificationSlice.ts';
import { RootState } from '../../redux/store.ts';
import NotificationItem from './NotificationItem.tsx';

const NotificationContainer = styled.div`
  position: fixed;
  top: 5px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
`;

const NotificationList: FC = () => {
  const notifications = useSelector((state: RootState) => state.notifications);
  const dispatch = useDispatch();

  useEffect(() => {
    notifications.forEach((notification: NotificationProps) => {
      if (notification.timeout) {
        const timer = setTimeout(
          () => dispatch(removeNotification(notification.id)),
          notification.timeout,
        );
        return () => clearTimeout(timer);
      }
    });
  }, [notifications, dispatch]);

  return (
    <NotificationContainer data-testid='notification-container'>
      {notifications.map((notification) => (
        <NotificationItem
          key={notification.id}
          notification={notification}
          onClose={() => dispatch(removeNotification(notification.id))}
          data-testid={`notification-item-${notification.id}`}
        />
      ))}
    </NotificationContainer>
  );
};

export default NotificationList;
