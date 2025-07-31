// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

import { uuidv4 } from '../../utils/util.ts';
import { NotificationProps } from '../../components/Notification/NotificationProps.ts';

const initialState: NotificationProps[] = [];

const notificationSlice = createSlice({
  name: 'notifications',
  initialState,
  reducers: {
    addNotification: (
      state,
      action: PayloadAction<Omit<NotificationProps, 'id'>>,
    ) => {
      const newNotification: NotificationProps = {
        ...action.payload,
        id: uuidv4(),
      };
      state.push(newNotification);
    },
    removeNotification: (state, action: PayloadAction<string>) => {
      return state.filter((notification) => notification.id !== action.payload);
    },
  },
});

export const { addNotification, removeNotification } =
  notificationSlice.actions;

export default notificationSlice.reducer;
