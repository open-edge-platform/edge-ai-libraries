// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { configureStore } from '@reduxjs/toolkit';
import { combineReducers } from 'redux';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import conversationReducer from '../redux/conversation/conversationSlice.ts';
import notificationReducer from '../redux/notification/notificationSlice.ts';
import { loadFromLocalStorage, saveToLocalStorage } from '../redux/store.ts';

vi.mock('react-redux', async () => {
  const actual = await vi.importActual('react-redux');
  return {
    ...actual,
    useDispatch: vi.fn(),
    useSelector: vi.fn(),
  };
});

describe('Redux Store Configuration test suite', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('should load state from local storage', () => {
    const state = { conversations: [], notifications: [] };
    localStorage.setItem('reduxStore', JSON.stringify(state));

    const loadedState = loadFromLocalStorage();
    expect(loadedState).toEqual(state);
  });

  it('should return undefined if no state is found in local storage', () => {
    const loadedState = loadFromLocalStorage();
    expect(loadedState).toBeUndefined();
  });

  it('should save state to local storage', () => {
    const state = {
      conversations: {
        conversations: [],
        files: [],
        isGenerating: false,
        onGoingResult: '',
        selectedConversationId: '',
      },
      notifications: [],
    };
    saveToLocalStorage(state);

    const savedState = localStorage.getItem('reduxStore');
    expect(savedState).toEqual(JSON.stringify(state));
  });

  it('should configure the store correctly', () => {
    const testStore = configureStore({
      reducer: combineReducers({
        conversations: conversationReducer,
        notifications: notificationReducer,
      }),
      devTools: true,
      preloadedState: undefined,
      middleware: (getDefaultMiddleware) => getDefaultMiddleware(),
    });

    expect(testStore.getState()).toEqual({
      conversations: {
        conversations: [],
        files: [],
        isGenerating: false,
        onGoingResult: '',
        selectedConversationId: '',
      },
      notifications: [],
    });
  });

  it('should subscribe to store changes and save state to local storage', () => {
    const testStore = configureStore({
      reducer: combineReducers({
        conversations: conversationReducer,
        notifications: notificationReducer,
      }),
      devTools: true,
      preloadedState: undefined,
      middleware: (getDefaultMiddleware) => getDefaultMiddleware(),
    });
    testStore.subscribe(() => saveToLocalStorage(testStore.getState()));

    testStore.dispatch({ type: 'TEST_ACTION' });

    expect(localStorage.getItem('reduxStore')).toEqual(
      JSON.stringify(testStore.getState()),
    );
  });
});
