// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest';
import { configureStore } from '@reduxjs/toolkit';
import { 
  VideoChunkActions, 
  VideoChunkReducer, 
  VideoChunkSelector 
} from '../redux/summary/videoChunkSlice';
import { 
  VideoChunkState,
  UIChunkForState
} from '../redux/summary/summary';
import { RootState } from '../redux/store';

// Mock store setup
const createMockStore = (initialState?: Partial<VideoChunkState>) => {
  return configureStore({
    reducer: {
      videoChunks: VideoChunkReducer,
    },
    preloadedState: {
      videoChunks: {
        chunks: {},
        selectedSummary: null,
        ...initialState,
      },
    },
  });
};

// Mock data factory
const createMockUIChunkForState = (overrides?: Partial<UIChunkForState>): UIChunkForState => ({
  stateId: 'test-state-1',
  chunkId: 'chunk-1',
  duration: {
    from: 0,
    to: 30,
  },
  ...overrides,
});

describe('VideoChunkSlice', () => {
  describe('Initial State', () => {
    it('should have correct initial state', () => {
      const store = createMockStore();
      const state = store.getState().videoChunks;
      
      expect(state.chunks).toEqual({});
      expect(state.selectedSummary).toBeNull();
    });
  });

  describe('Reducers', () => {
    describe('setSelectedSummary', () => {
      it('should set the selected summary', () => {
        const store = createMockStore();
        
        store.dispatch(VideoChunkActions.setSelectedSummary('state-1'));
        
        const state = store.getState().videoChunks;
        expect(state.selectedSummary).toBe('state-1');
      });

      it('should update selected summary when called multiple times', () => {
        const store = createMockStore();
        
        store.dispatch(VideoChunkActions.setSelectedSummary('state-1'));
        store.dispatch(VideoChunkActions.setSelectedSummary('state-2'));
        
        const state = store.getState().videoChunks;
        expect(state.selectedSummary).toBe('state-2');
      });

      it('should handle setting selected summary from null', () => {
        const store = createMockStore({ selectedSummary: null });
        
        store.dispatch(VideoChunkActions.setSelectedSummary('new-state'));
        
        const state = store.getState().videoChunks;
        expect(state.selectedSummary).toBe('new-state');
      });

      it('should handle setting selected summary to same value', () => {
        const store = createMockStore({ selectedSummary: 'existing-state' });
        
        store.dispatch(VideoChunkActions.setSelectedSummary('existing-state'));
        
        const state = store.getState().videoChunks;
        expect(state.selectedSummary).toBe('existing-state');
      });
    });

    describe('addChunks', () => {
      it('should add chunks to the state with correct key format', () => {
        const store = createMockStore();
        const mockChunks: UIChunkForState[] = [
          createMockUIChunkForState({
            stateId: 'state-1',
            chunkId: 'chunk-1',
            duration: { from: 0, to: 30 },
          }),
          createMockUIChunkForState({
            stateId: 'state-1',
            chunkId: 'chunk-2',
            duration: { from: 30, to: 60 },
          }),
        ];
        
        store.dispatch(VideoChunkActions.addChunks(mockChunks));
        
        const state = store.getState().videoChunks;
        expect(Object.keys(state.chunks)).toHaveLength(2);
        expect(state.chunks['state-1#chunk-1']).toBeDefined();
        expect(state.chunks['state-1#chunk-2']).toBeDefined();
        expect(state.chunks['state-1#chunk-1'].duration.from).toBe(0);
        expect(state.chunks['state-1#chunk-1'].duration.to).toBe(30);
        expect(state.chunks['state-1#chunk-2'].duration.from).toBe(30);
        expect(state.chunks['state-1#chunk-2'].duration.to).toBe(60);
      });

      it('should handle chunks from different states', () => {
        const store = createMockStore();
        const mockChunks: UIChunkForState[] = [
          createMockUIChunkForState({
            stateId: 'state-1',
            chunkId: 'chunk-1',
            duration: { from: 0, to: 30 },
          }),
          createMockUIChunkForState({
            stateId: 'state-2',
            chunkId: 'chunk-1',
            duration: { from: 0, to: 45 },
          }),
        ];
        
        store.dispatch(VideoChunkActions.addChunks(mockChunks));
        
        const state = store.getState().videoChunks;
        expect(Object.keys(state.chunks)).toHaveLength(2);
        expect(state.chunks['state-1#chunk-1']).toBeDefined();
        expect(state.chunks['state-2#chunk-1']).toBeDefined();
        expect(state.chunks['state-1#chunk-1'].stateId).toBe('state-1');
        expect(state.chunks['state-2#chunk-1'].stateId).toBe('state-2');
        expect(state.chunks['state-1#chunk-1'].duration.to).toBe(30);
        expect(state.chunks['state-2#chunk-1'].duration.to).toBe(45);
      });

      it('should merge with existing chunks', () => {
        const existingChunk = createMockUIChunkForState({
          stateId: 'state-1',
          chunkId: 'chunk-existing',
          duration: { from: 60, to: 90 },
        });
        const store = createMockStore({
          chunks: {
            'state-1#chunk-existing': existingChunk,
          },
        });
        
        const newChunks: UIChunkForState[] = [
          createMockUIChunkForState({
            stateId: 'state-1',
            chunkId: 'chunk-new',
            duration: { from: 90, to: 120 },
          }),
        ];
        
        store.dispatch(VideoChunkActions.addChunks(newChunks));
        
        const state = store.getState().videoChunks;
        expect(Object.keys(state.chunks)).toHaveLength(2);
        expect(state.chunks['state-1#chunk-existing']).toBeDefined();
        expect(state.chunks['state-1#chunk-new']).toBeDefined();
        expect(state.chunks['state-1#chunk-existing'].duration.to).toBe(90);
        expect(state.chunks['state-1#chunk-new'].duration.to).toBe(120);
      });

      it('should overwrite existing chunks with same key', () => {
        const existingChunk = createMockUIChunkForState({
          stateId: 'state-1',
          chunkId: 'chunk-1',
          duration: { from: 0, to: 30 },
        });
        const store = createMockStore({
          chunks: {
            'state-1#chunk-1': existingChunk,
          },
        });
        
        const updatedChunks: UIChunkForState[] = [
          createMockUIChunkForState({
            stateId: 'state-1',
            chunkId: 'chunk-1',
            duration: { from: 0, to: 45 }, // Updated duration
          }),
        ];
        
        store.dispatch(VideoChunkActions.addChunks(updatedChunks));
        
        const state = store.getState().videoChunks;
        expect(Object.keys(state.chunks)).toHaveLength(1);
        expect(state.chunks['state-1#chunk-1'].duration.to).toBe(45);
      });

      it('should handle empty chunks array', () => {
        const store = createMockStore();
        
        store.dispatch(VideoChunkActions.addChunks([]));
        
        const state = store.getState().videoChunks;
        expect(Object.keys(state.chunks)).toHaveLength(0);
        expect(state.chunks).toEqual({});
      });

      it('should handle single chunk', () => {
        const store = createMockStore();
        const mockChunk: UIChunkForState[] = [
          createMockUIChunkForState({
            stateId: 'state-1',
            chunkId: 'single-chunk',
            duration: { from: 0, to: 120 },
          }),
        ];
        
        store.dispatch(VideoChunkActions.addChunks(mockChunk));
        
        const state = store.getState().videoChunks;
        expect(Object.keys(state.chunks)).toHaveLength(1);
        expect(state.chunks['state-1#single-chunk']).toBeDefined();
        expect(state.chunks['state-1#single-chunk'].duration.to).toBe(120);
      });

      it('should handle chunks with complex stateId and chunkId', () => {
        const store = createMockStore();
        const mockChunks: UIChunkForState[] = [
          createMockUIChunkForState({
            stateId: 'complex-state-with-dashes',
            chunkId: 'chunk-with-special-chars_123',
            duration: { from: 0, to: 30 },
          }),
        ];
        
        store.dispatch(VideoChunkActions.addChunks(mockChunks));
        
        const state = store.getState().videoChunks;
        const expectedKey = 'complex-state-with-dashes#chunk-with-special-chars_123';
        expect(state.chunks[expectedKey]).toBeDefined();
        expect(state.chunks[expectedKey].stateId).toBe('complex-state-with-dashes');
        expect(state.chunks[expectedKey].chunkId).toBe('chunk-with-special-chars_123');
      });
    });
  });

  describe('VideoChunkSelector', () => {
    describe('with no selected summary', () => {
      it('should return empty chunk keys', () => {
        const mockRootState = {
          videoChunks: { chunks: {}, selectedSummary: null },
        } as unknown as RootState;
        
        const result = VideoChunkSelector(mockRootState);
        
        expect(result.chunkKeys).toEqual([]);
        expect(result.chunkData).toEqual({});
      });

      it('should return chunk data even without selection', () => {
        const chunk1 = createMockUIChunkForState({
          stateId: 'state-1',
          chunkId: 'chunk-1',
        });
        
        const mockRootState = {
          videoChunks: {
            chunks: {
              'state-1#chunk-1': chunk1,
            },
            selectedSummary: null,
          },
        } as unknown as RootState;
        
        const result = VideoChunkSelector(mockRootState);
        
        expect(result.chunkKeys).toEqual([]);
        expect(result.chunkData).toEqual({
          'state-1#chunk-1': chunk1,
        });
      });
    });

    describe('with selected summary', () => {
      it('should return chunk keys for selected summary only', () => {
        const chunk1 = createMockUIChunkForState({
          stateId: 'state-1',
          chunkId: 'chunk-1',
        });
        const chunk2 = createMockUIChunkForState({
          stateId: 'state-1',
          chunkId: 'chunk-2',
        });
        const chunk3 = createMockUIChunkForState({
          stateId: 'state-2',
          chunkId: 'chunk-1',
        });
        
        const mockRootState = {
          videoChunks: {
            chunks: {
              'state-1#chunk-1': chunk1,
              'state-1#chunk-2': chunk2,
              'state-2#chunk-1': chunk3,
            },
            selectedSummary: 'state-1',
          },
        } as unknown as RootState;
        
        const result = VideoChunkSelector(mockRootState);
        
        expect(result.chunkKeys).toHaveLength(2);
        expect(result.chunkKeys).toContain('state-1#chunk-1');
        expect(result.chunkKeys).toContain('state-1#chunk-2');
        expect(result.chunkKeys).not.toContain('state-2#chunk-1');
      });

      it('should return all chunk data regardless of selection', () => {
        const chunk1 = createMockUIChunkForState({
          stateId: 'state-1',
          chunkId: 'chunk-1',
        });
        const chunk2 = createMockUIChunkForState({
          stateId: 'state-2',
          chunkId: 'chunk-1',
        });
        
        const mockRootState = {
          videoChunks: {
            chunks: {
              'state-1#chunk-1': chunk1,
              'state-2#chunk-1': chunk2,
            },
            selectedSummary: 'state-1',
          },
        } as unknown as RootState;
        
        const result = VideoChunkSelector(mockRootState);
        
        expect(result.chunkData).toEqual({
          'state-1#chunk-1': chunk1,
          'state-2#chunk-1': chunk2,
        });
      });

      it('should handle selected summary with no matching chunks', () => {
        const chunk1 = createMockUIChunkForState({
          stateId: 'state-1',
          chunkId: 'chunk-1',
        });
        
        const mockRootState = {
          videoChunks: {
            chunks: {
              'state-1#chunk-1': chunk1,
            },
            selectedSummary: 'state-non-existent',
          },
        } as unknown as RootState;
        
        const result = VideoChunkSelector(mockRootState);
        
        expect(result.chunkKeys).toEqual([]);
        expect(result.chunkData).toEqual({
          'state-1#chunk-1': chunk1,
        });
      });

      it('should maintain chunk key order based on input order', () => {
        // Since Object.values() maintains insertion order in modern JS
        const chunk1 = createMockUIChunkForState({
          stateId: 'state-1',
          chunkId: 'chunk-z',
        });
        const chunk2 = createMockUIChunkForState({
          stateId: 'state-1',
          chunkId: 'chunk-a',
        });
        const chunk3 = createMockUIChunkForState({
          stateId: 'state-1',
          chunkId: 'chunk-m',
        });
        
        const mockRootState = {
          videoChunks: {
            chunks: {
              'state-1#chunk-z': chunk1,
              'state-1#chunk-a': chunk2,
              'state-1#chunk-m': chunk3,
            },
            selectedSummary: 'state-1',
          },
        } as unknown as RootState;
        
        const result = VideoChunkSelector(mockRootState);
        
        expect(result.chunkKeys).toEqual([
          'state-1#chunk-z',
          'state-1#chunk-a', 
          'state-1#chunk-m'
        ]);
      });

      it('should handle empty chunks with selected summary', () => {
        const mockRootState = {
          videoChunks: {
            chunks: {},
            selectedSummary: 'state-1',
          },
        } as unknown as RootState;
        
        const result = VideoChunkSelector(mockRootState);
        
        expect(result.chunkKeys).toEqual([]);
        expect(result.chunkData).toEqual({});
      });
    });

    describe('edge cases', () => {
      it('should handle null chunkData by throwing error', () => {
        const mockRootState = {
          videoChunks: {
            chunks: null,
            selectedSummary: 'state-1',
          },
        } as unknown as RootState;
        
        // The selector will throw an error when chunks is null and selectedSummary is not null
        expect(() => {
          VideoChunkSelector(mockRootState);
        }).toThrow();
      });

      it('should handle undefined chunkData by throwing error', () => {
        const mockRootState = {
          videoChunks: {
            chunks: undefined,
            selectedSummary: 'state-1',
          },
        } as unknown as RootState;
        
        // The selector will throw an error when chunks is undefined and selectedSummary is not null
        expect(() => {
          VideoChunkSelector(mockRootState);
        }).toThrow();
      });

      it('should handle null chunkData with no selected summary', () => {
        const mockRootState = {
          videoChunks: {
            chunks: null,
            selectedSummary: null,
          },
        } as unknown as RootState;
        
        const result = VideoChunkSelector(mockRootState);
        
        expect(result.chunkData).toBeNull();
        expect(result.chunkKeys).toEqual([]);
      });
    });
  });
});
