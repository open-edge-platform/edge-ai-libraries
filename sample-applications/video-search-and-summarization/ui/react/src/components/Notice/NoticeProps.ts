// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { ReactNode, SetStateAction, Dispatch } from 'react';

export enum NoticeKind {
  SUCCESS = 'success',
  WARNING = 'warning',
  ERROR = 'error',
  INFO = 'info',
  DEFAULT = 'default',
}

export interface NoticeProps {
  message?: ReactNode;
  kind?: NoticeKind;
  isNoticeVisible: boolean;
  setIsNoticeVisible: Dispatch<SetStateAction<boolean>>;
}
