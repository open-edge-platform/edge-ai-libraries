// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { combineReducers, configureStore } from '@reduxjs/toolkit';
import { TypedUseSelectorHook, useDispatch, useSelector } from 'react-redux';

import conversationReducer from './conversation/conversationSlice.ts';
import notificationReducer from './notification/notificationSlice.ts';

export const loadFromLocalStorage = () => {
  try {
    const serialisedState = localStorage.getItem('reduxStore');
    if (serialisedState === null) {
      return undefined;
    }
    return JSON.parse(serialisedState);
  } catch (err) {
    console.warn(err);
    return undefined;
  }
};

export const saveToLocalStorage = (
  state: ReturnType<typeof store.getState>,
) => {
  try {
    const serialState = JSON.stringify(state);
    localStorage.setItem('reduxStore', serialState);
  } catch (e) {
    console.warn(e);
  }
};

const store = configureStore({
  reducer: combineReducers({
    conversations: conversationReducer,
    notifications: notificationReducer,
  }),
  devTools: import.meta.env.PROD || true,
  preloadedState: loadFromLocalStorage(),
  middleware: (getDefaultMiddleware) => getDefaultMiddleware(),
});

store.subscribe(() => saveToLocalStorage(store.getState()));

export type AppDispatch = typeof store.dispatch;
export type RootState = ReturnType<typeof store.getState>;

export const useAppDispatch: () => AppDispatch = useDispatch;
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;

export default store;
