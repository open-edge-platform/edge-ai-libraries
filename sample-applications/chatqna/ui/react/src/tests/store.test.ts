// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { configureStore } from '@reduxjs/toolkit';
import { combineReducers } from 'redux';
import { it, expect, describe, vi, beforeEach } from 'vitest';

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

  it('should configure the store with the correct reducers', () => {
    const testStore = configureStore({
      reducer: combineReducers({
        conversations: conversationReducer,
        notifications: notificationReducer,
      }),
    });

    expect(testStore.getState().conversations).toEqual(
      conversationReducer(undefined, { type: 'unknown' }),
    );
    expect(testStore.getState().notifications).toEqual(
      notificationReducer(undefined, { type: 'unknown' }),
    );
  });

  it('should load state from localStorage', () => {
    const mockState = {
      conversations: [],
      notifications: [],
    };
    localStorage.setItem('reduxStore', JSON.stringify(mockState));
    const loadedState = loadFromLocalStorage();

    expect(loadedState).toEqual(mockState);
  });

  it('should return undefined if localStorage is empty', () => {
    const loadedState = loadFromLocalStorage();
    expect(loadedState).toBeUndefined();
  });

  it('should save state to localStorage', () => {
    const mockState = {
      conversations: {
        selectedConversationId: '',
        conversations: [],
        onGoingResult: '',
        files: [],
        links: [],
        isGenerating: false,
      },
      notifications: [],
    };
    saveToLocalStorage(mockState);
    expect(localStorage.getItem('reduxStore')).toEqual(
      JSON.stringify(mockState),
    );
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
        links: [],
        isGenerating: false,
        onGoingResult: '',
        selectedConversationId: '',
      },
      notifications: [],
    });
  });

  it('should subscribe to store changes and save state to localStorage', () => {
    const testStore = configureStore({
      reducer: combineReducers({
        conversations: conversationReducer,
        notifications: notificationReducer,
      }),
    });

    testStore.subscribe(() => saveToLocalStorage(testStore.getState()));
    testStore.dispatch({ type: 'user/setUser', payload: 'John Doe' });

    expect(localStorage.getItem('reduxStore')).toEqual(
      JSON.stringify(testStore.getState()),
    );
  });
});
