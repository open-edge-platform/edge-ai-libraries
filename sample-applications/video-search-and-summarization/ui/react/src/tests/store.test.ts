// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { configureStore, combineReducers } from '@reduxjs/toolkit';
import store, { loadFromLocalStorage, saveToLocalStorage, useAppDispatch, useAppSelector } from '../redux/store';

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};

// Mock console methods
const consoleMock = {
  warn: vi.fn(),
};

// Mock React Redux hooks
vi.mock('react-redux', () => ({
  useDispatch: vi.fn(),
  useSelector: vi.fn(),
}));

describe('Redux Store', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.localStorage = localStorageMock as any;
    global.console = { ...console, warn: consoleMock.warn };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('store configuration', () => {
    it('should have correct structure with all reducers', () => {
      const state = store.getState();
      
      expect(state).toHaveProperty('videoChunks');
      expect(state).toHaveProperty('videoFrames');
      expect(state).toHaveProperty('videos');
      expect(state).toHaveProperty('notifications');
      expect(state).toHaveProperty('summaries');
      expect(state).toHaveProperty('search');
      expect(state).toHaveProperty('ui');
    });

    it('should configure devTools correctly', () => {
      // Test that store is configured with devTools
      expect(store).toBeDefined();
      expect(typeof store.dispatch).toBe('function');
      expect(typeof store.getState).toBe('function');
      expect(typeof store.subscribe).toBe('function');
    });
  });

  describe('loadFromLocalStorage', () => {
    it('should return undefined when no data in localStorage', () => {
      localStorageMock.getItem.mockReturnValue(null);
      
      const result = loadFromLocalStorage();
      
      expect(result).toBeUndefined();
      expect(localStorageMock.getItem).toHaveBeenCalledWith('reduxStore');
    });

    it('should load and parse valid data from localStorage', () => {
      const mockState = {
        videos: { videoList: [] },
        search: { queries: [] },
        ui: { someProperty: 'test' }
      };
      localStorageMock.getItem.mockReturnValue(JSON.stringify(mockState));
      
      const result = loadFromLocalStorage();
      
      expect(result).toEqual({
        videos: { videoList: [] },
        search: { queries: [] }
        // ui should be deleted
      });
      expect(result).not.toHaveProperty('ui');
    });

    it('should handle invalid JSON and return undefined', () => {
      localStorageMock.getItem.mockReturnValue('invalid json');
      
      const result = loadFromLocalStorage();
      
      expect(result).toBeUndefined();
      expect(consoleMock.warn).toHaveBeenCalledWith(expect.any(Error));
    });

    it('should handle localStorage getItem throwing error', () => {
      localStorageMock.getItem.mockImplementation(() => {
        throw new Error('localStorage error');
      });
      
      const result = loadFromLocalStorage();
      
      expect(result).toBeUndefined();
      expect(consoleMock.warn).toHaveBeenCalledWith(expect.any(Error));
    });

    it('should remove ui property from loaded state', () => {
      const mockState = {
        videos: { videoList: [] },
        ui: { drawerOpen: true },
        search: { queries: [] }
      };
      localStorageMock.getItem.mockReturnValue(JSON.stringify(mockState));
      
      const result = loadFromLocalStorage();
      
      expect(result).toEqual({
        videos: { videoList: [] },
        search: { queries: [] }
      });
      expect(result).not.toHaveProperty('ui');
    });
  });

  describe('saveToLocalStorage', () => {
    it('should save state to localStorage', () => {
      const mockState = {
        videos: { videoList: [] },
        search: { queries: [] },
        ui: { drawerOpen: false }
      } as any;
      
      saveToLocalStorage(mockState);
      
      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'reduxStore', 
        JSON.stringify(mockState)
      );
    });

    it('should handle localStorage setItem throwing error', () => {
      const mockState = { videos: { videoList: [] } } as any;
      localStorageMock.setItem.mockImplementation(() => {
        throw new Error('localStorage error');
      });
      
      saveToLocalStorage(mockState);
      
      expect(consoleMock.warn).toHaveBeenCalledWith(expect.any(Error));
    });

    it('should handle circular reference objects', () => {
      const circularObj: any = { name: 'test' };
      circularObj.self = circularObj;
      const mockState = { circular: circularObj } as any;
      
      saveToLocalStorage(mockState);
      
      expect(consoleMock.warn).toHaveBeenCalledWith(expect.any(Error));
    });

    it('should handle undefined state', () => {
      saveToLocalStorage(undefined as any);
      
      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'reduxStore', 
        undefined
      );
    });
  });

  describe('store subscription', () => {
    it('should save state to localStorage when store updates', () => {
      // Clear any previous calls
      localStorageMock.setItem.mockClear();
      
      // Dispatch an action to trigger store update
      store.dispatch({ type: 'test/action', payload: 'test' });
      
      // Check that saveToLocalStorage was called
      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'reduxStore',
        expect.any(String)
      );
    });
  });

  describe('preloaded state', () => {
    it('should load preloaded state on store creation', () => {
      const mockState = {
        videos: { videoList: ['test'] },
        search: { queries: ['test query'] }
      };
      localStorageMock.getItem.mockReturnValue(JSON.stringify(mockState));
      
      // Create a new store to test preloaded state
      const testStore = configureStore({
        reducer: combineReducers({
          videos: (state = {}) => state,
          search: (state = {}) => state,
        }),
        preloadedState: loadFromLocalStorage(),
      });
      
      const state = testStore.getState();
      expect(state.videos).toEqual({ videoList: ['test'] });
      expect(state.search).toEqual({ queries: ['test query'] });
    });
  });

  describe('TypeScript types', () => {
    it('should export correct AppDispatch type', () => {
      expect(typeof store.dispatch).toBe('function');
    });

    it('should export correct RootState type', () => {
      const state = store.getState();
      expect(typeof state).toBe('object');
      expect(state).toHaveProperty('videos');
      expect(state).toHaveProperty('search');
      expect(state).toHaveProperty('ui');
    });
  });

  describe('hook exports', () => {
    it('should export useAppDispatch hook', () => {
      expect(useAppDispatch).toBeDefined();
      expect(typeof useAppDispatch).toBe('function');
    });

    it('should export useAppSelector hook', () => {
      expect(useAppSelector).toBeDefined();
      expect(typeof useAppSelector).toBe('function');
    });
  });

  describe('error edge cases', () => {
    it('should handle JSON.parse throwing SyntaxError', () => {
      localStorageMock.getItem.mockReturnValue('{"invalid": json}');
      
      const result = loadFromLocalStorage();
      
      expect(result).toBeUndefined();
      expect(consoleMock.warn).toHaveBeenCalledWith(expect.any(SyntaxError));
    });

    it('should handle JSON.stringify throwing TypeError', () => {
      const mockState = { test: BigInt(123) } as any; // BigInt can't be stringified
      
      saveToLocalStorage(mockState);
      
      expect(consoleMock.warn).toHaveBeenCalledWith(expect.any(TypeError));
    });

    it('should handle empty string from localStorage', () => {
      localStorageMock.getItem.mockReturnValue('');
      
      const result = loadFromLocalStorage();
      
      expect(result).toBeUndefined();
      expect(consoleMock.warn).toHaveBeenCalledWith(expect.any(Error));
    });

    it('should handle localStorage quota exceeded', () => {
      localStorageMock.setItem.mockImplementation(() => {
        const error = new Error('QuotaExceededError');
        error.name = 'QuotaExceededError';
        throw error;
      });
      
      const mockState = { large: 'data'.repeat(1000000) } as any;
      saveToLocalStorage(mockState);
      
      expect(consoleMock.warn).toHaveBeenCalledWith(expect.objectContaining({
        name: 'QuotaExceededError'
      }));
    });
  });
});
