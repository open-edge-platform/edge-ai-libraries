// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { InlineNotification } from '@carbon/react';
import { type FC, useState, useEffect } from 'react';
import styled, { keyframes } from 'styled-components';

import { NotificationItemProps } from './NotificationProps.ts';

const slideDown = keyframes`
  from {
    top: -50px;
    opacity: 0;
  }
  to {
    top: 5px;
    opacity: 1;
  }
`;

const NotificationWrapper = styled.div`
  margin: 0.5rem 0;
  position: relative;
  opacity: 1;
  animation: ${slideDown} 0.2s ease-out;
`;

const ProgressBar = styled.div`
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  height: 2px;
`;

const Progress = styled.div<{ kind: string; progress: number }>`
  height: 100%;
  transition: width 0.1s linear;
  width: ${({ progress }) => `${progress}%`};
  background-color: ${({ kind }) => `var(--color-${kind})`};
`;

const NotificationItem: FC<NotificationItemProps> = ({
  notification,
  onClose,
}) => {
  const { timeout, kind, title } = notification;
  const [progress, setProgress] = useState(100);

  useEffect(() => {
    if (timeout) {
      const interval = setInterval(() => {
        setProgress((prev) => (prev > 0 ? prev - 100 / (timeout / 100) : 0));
      }, 100);

      return () => clearInterval(interval);
    }
  }, [timeout]);

  // To remove the warning
  useEffect(() => {
    const button = document.querySelector('button[aria-hidden="true"]');
    if (button) {
      button.setAttribute('aria-hidden', 'false');
    }
  }, []);

  return (
    <NotificationWrapper data-testid={`notification-item-${notification.id}`}>
      <InlineNotification
        kind={kind}
        title={title}
        onCloseButtonClick={onClose}
        data-testid='inline-notification'
      />
      {timeout && (
        <ProgressBar data-testid='progress-bar'>
          <Progress kind={kind} progress={progress} data-testid='progress' />
        </ProgressBar>
      )}
    </NotificationWrapper>
  );
};

export default NotificationItem;
