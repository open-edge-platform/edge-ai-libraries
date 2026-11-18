// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// One slice per domain concern (see the reference app's src/redux/slices/
// for examples: uiSlice, transcriptSlice, ...). Keep slices small and
// focused; avoid a single catch-all slice.

import { configureStore } from '@reduxjs/toolkit';
import uiReducer from './slices/uiSlice';

export const store = configureStore({
  reducer: {
    ui: uiReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
