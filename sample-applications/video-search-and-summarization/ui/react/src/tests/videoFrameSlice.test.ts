// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { configureStore } from '@reduxjs/toolkit';
import { 
  VideoFramesAction, 
  VideoFrameReducer, 
  VideoFrameSelector 
} from '../redux/summary/videoFrameSlice';
import { 
  VideoFrameState,
  UIFrameForState, 
  UIFrameSummary, 
  StateActionStatus
} from '../redux/summary/summary';
import { RootState } from '../redux/store';

// Console.log is used in the selector, mock it to avoid test noise
beforeEach(() => {
  vi.spyOn(console, 'log').mockImplementation(() => {});
});

// Mock store setup
const createMockStore = (initialState?: Partial<VideoFrameState>) => {
  return configureStore({
    reducer: {
      videoFrames: VideoFrameReducer,
    },
    preloadedState: {
      videoFrames: {
        frames: {},
        frameSummaries: {},
        selectedSummary: null,
        ...initialState,
      },
    },
  });
};

// Mock data factories
const createMockUIFrameForState = (overrides?: Partial<UIFrameForState>): UIFrameForState => ({
  stateId: 'test-state-1',
  chunkId: 'chunk-1',
  frameId: 'frame-1',
  url: 'test-frame-url.jpg',
  metadata: {
    objects: [],
    resolution: { height: 480, width: 640 },
    system_timestamp: '2024-01-01T10:00:00Z',
    timestamp: 1000,
    time: '00:01:00',
    image_format: 'jpeg',
  },
  videoTimeStamp: 1000,
  ...overrides,
});

const createMockUIFrameSummary = (overrides?: Partial<UIFrameSummary>): UIFrameSummary => ({
  summary: 'Test frame summary',
  frames: ['frame-1', 'frame-2'],
  frameKey: 'frame-key-1',
  startFrame: 'frame-1',
  endFrame: 'frame-2',
  status: StateActionStatus.COMPLETE,
  stateId: 'test-state-1',
  ...overrides,
});

describe('VideoFrameSlice', () => {
  describe('Initial State', () => {
    it('should have correct initial state', () => {
      const store = createMockStore();
      const state = store.getState().videoFrames;
      
      expect(state.frames).toEqual({});
      expect(state.frameSummaries).toEqual({});
      expect(state.selectedSummary).toBeNull();
    });
  });

  describe('Reducers', () => {
    describe('addFrames', () => {
      it('should add frames to the state with correct key format', () => {
        const store = createMockStore();
        const mockFrames: UIFrameForState[] = [
          createMockUIFrameForState({
            stateId: 'state-1',
            chunkId: 'chunk-1',
            frameId: 'frame-1',
          }),
          createMockUIFrameForState({
            stateId: 'state-1',
            chunkId: 'chunk-1',
            frameId: 'frame-2',
          }),
        ];
        
        store.dispatch(VideoFramesAction.addFrames(mockFrames));
        
        const state = store.getState().videoFrames;
        expect(Object.keys(state.frames)).toHaveLength(2);
        expect(state.frames['state-1#chunk-1#frame-1']).toBeDefined();
        expect(state.frames['state-1#chunk-1#frame-2']).toBeDefined();
        expect(state.frames['state-1#chunk-1#frame-1'].url).toBe('test-frame-url.jpg');
      });

      it('should handle frames from different states and chunks', () => {
        const store = createMockStore();
        const mockFrames: UIFrameForState[] = [
          createMockUIFrameForState({
            stateId: 'state-1',
            chunkId: 'chunk-1',
            frameId: 'frame-1',
          }),
          createMockUIFrameForState({
            stateId: 'state-2',
            chunkId: 'chunk-2',
            frameId: 'frame-1',
          }),
        ];
        
        store.dispatch(VideoFramesAction.addFrames(mockFrames));
        
        const state = store.getState().videoFrames;
        expect(state.frames['state-1#chunk-1#frame-1']).toBeDefined();
        expect(state.frames['state-2#chunk-2#frame-1']).toBeDefined();
        expect(state.frames['state-1#chunk-1#frame-1'].stateId).toBe('state-1');
        expect(state.frames['state-2#chunk-2#frame-1'].stateId).toBe('state-2');
      });

      it('should merge with existing frames', () => {
        const existingFrame = createMockUIFrameForState({
          stateId: 'state-1',
          chunkId: 'chunk-1',
          frameId: 'frame-existing',
        });
        const store = createMockStore({
          frames: {
            'state-1#chunk-1#frame-existing': existingFrame,
          },
        });
        
        const newFrames: UIFrameForState[] = [
          createMockUIFrameForState({
            stateId: 'state-1',
            chunkId: 'chunk-1',
            frameId: 'frame-new',
          }),
        ];
        
        store.dispatch(VideoFramesAction.addFrames(newFrames));
        
        const state = store.getState().videoFrames;
        expect(Object.keys(state.frames)).toHaveLength(2);
        expect(state.frames['state-1#chunk-1#frame-existing']).toBeDefined();
        expect(state.frames['state-1#chunk-1#frame-new']).toBeDefined();
      });

      it('should handle empty frames array', () => {
        const store = createMockStore();
        
        store.dispatch(VideoFramesAction.addFrames([]));
        
        const state = store.getState().videoFrames;
        expect(Object.keys(state.frames)).toHaveLength(0);
      });
    });

    describe('updateFrameSummary', () => {
      it('should add frame summary with correct key format', () => {
        const store = createMockStore();
        const mockFrameSummary = createMockUIFrameSummary({
          stateId: 'state-1',
          frameKey: 'frame-key-1',
          summary: 'Test summary content',
        });
        
        store.dispatch(VideoFramesAction.updateFrameSummary(mockFrameSummary));
        
        const state = store.getState().videoFrames;
        expect(state.frameSummaries['state-1#frame-key-1']).toBeDefined();
        expect(state.frameSummaries['state-1#frame-key-1'].summary).toBe('Test summary content');
        expect(state.frameSummaries['state-1#frame-key-1'].status).toBe(StateActionStatus.COMPLETE);
      });

      it('should update existing frame summary', () => {
        const existingSummary = createMockUIFrameSummary({
          stateId: 'state-1',
          frameKey: 'frame-key-1',
          summary: 'Old summary',
          status: StateActionStatus.IN_PROGRESS,
        });
        const store = createMockStore({
          frameSummaries: {
            'state-1#frame-key-1': existingSummary,
          },
        });
        
        const updatedSummary = createMockUIFrameSummary({
          stateId: 'state-1',
          frameKey: 'frame-key-1',
          summary: 'Updated summary',
          status: StateActionStatus.COMPLETE,
        });
        
        store.dispatch(VideoFramesAction.updateFrameSummary(updatedSummary));
        
        const state = store.getState().videoFrames;
        expect(state.frameSummaries['state-1#frame-key-1'].summary).toBe('Updated summary');
        expect(state.frameSummaries['state-1#frame-key-1'].status).toBe(StateActionStatus.COMPLETE);
      });
    });

    describe('selectSummary', () => {
      it('should set the selected summary', () => {
        const store = createMockStore();
        
        store.dispatch(VideoFramesAction.selectSummary('state-1'));
        
        const state = store.getState().videoFrames;
        expect(state.selectedSummary).toBe('state-1');
      });

      it('should update selected summary', () => {
        const store = createMockStore({ selectedSummary: 'old-state' });
        
        store.dispatch(VideoFramesAction.selectSummary('new-state'));
        
        const state = store.getState().videoFrames;
        expect(state.selectedSummary).toBe('new-state');
      });
    });
  });

  describe('VideoFrameSelector', () => {
    describe('with no selected summary', () => {
      it('should return empty arrays and empty functions', () => {
        const mockRootState = {
          videoFrames: { frames: {}, frameSummaries: {}, selectedSummary: null },
        } as unknown as RootState;
        
        const result = VideoFrameSelector(mockRootState);
        
        expect(result.frameKeys('chunk-1')).toEqual([]);
        expect(result.frameSummaries).toEqual([]);
        expect(result.frames).toEqual([]);
        expect(result.frameData('any-key')).toBeNull();
      });
    });

    describe('with selected summary', () => {
      it('should return correct frame keys for a chunk', () => {
        const frame1 = createMockUIFrameForState({
          stateId: 'state-1',
          chunkId: 'chunk-1',
          frameId: 'frame-1',
        });
        const frame2 = createMockUIFrameForState({
          stateId: 'state-1',
          chunkId: 'chunk-1',
          frameId: 'frame-2',
        });
        const frame3 = createMockUIFrameForState({
          stateId: 'state-1',
          chunkId: 'chunk-2',
          frameId: 'frame-3',
        });
        
        const mockRootState = {
          videoFrames: {
            frames: {
              'state-1#chunk-1#frame-1': frame1,
              'state-1#chunk-1#frame-2': frame2,
              'state-1#chunk-2#frame-3': frame3,
            },
            frameSummaries: {},
            selectedSummary: 'state-1',
          },
        } as unknown as RootState;
        
        const result = VideoFrameSelector(mockRootState);
        
        const chunk1Keys = result.frameKeys('chunk-1');
        expect(chunk1Keys).toHaveLength(2);
        expect(chunk1Keys).toContain('state-1#chunk-1#frame-1');
        expect(chunk1Keys).toContain('state-1#chunk-1#frame-2');
        
        const chunk2Keys = result.frameKeys('chunk-2');
        expect(chunk2Keys).toHaveLength(1);
        expect(chunk2Keys).toContain('state-1#chunk-2#frame-3');
      });

      it('should return sorted frame summaries for selected summary', () => {
        const summary1 = createMockUIFrameSummary({
          stateId: 'state-1',
          frameKey: 'key-1',
          startFrame: '3',
          summary: 'Summary 1',
        });
        const summary2 = createMockUIFrameSummary({
          stateId: 'state-1',
          frameKey: 'key-2',
          startFrame: '1',
          summary: 'Summary 2',
        });
        const summary3 = createMockUIFrameSummary({
          stateId: 'state-2',
          frameKey: 'key-3',
          startFrame: '2',
          summary: 'Summary 3',
        });
        
        const mockRootState = {
          videoFrames: {
            frames: {},
            frameSummaries: {
              'state-1#key-1': summary1,
              'state-1#key-2': summary2,
              'state-2#key-3': summary3,
            },
            selectedSummary: 'state-1',
          },
        } as unknown as RootState;
        
        const result = VideoFrameSelector(mockRootState);
        
        expect(result.frameSummaries).toHaveLength(2);
        expect(result.frameSummaries[0].summary).toBe('Summary 2'); // startFrame '1'
        expect(result.frameSummaries[1].summary).toBe('Summary 1'); // startFrame '3'
      });

      it('should count frame summary status correctly', () => {
        const summary1 = createMockUIFrameSummary({
          stateId: 'state-1',
          status: StateActionStatus.COMPLETE,
        });
        const summary2 = createMockUIFrameSummary({
          stateId: 'state-1',
          frameKey: 'key-2',
          status: StateActionStatus.IN_PROGRESS,
        });
        const summary3 = createMockUIFrameSummary({
          stateId: 'state-1',
          frameKey: 'key-3',
          status: StateActionStatus.COMPLETE,
        });
        
        const mockRootState = {
          videoFrames: {
            frames: {},
            frameSummaries: {
              'state-1#frame-key-1': summary1,
              'state-1#key-2': summary2,
              'state-1#key-3': summary3,
            },
            selectedSummary: 'state-1',
          },
        } as unknown as RootState;
        
        const result = VideoFrameSelector(mockRootState);
        
        expect(result.frameSummaryStatusCount).toEqual({
          ready: 0,
          inProgress: 1,
          complete: 2,
          na: 0,
        });
      });

      it('should return sorted frames for selected summary', () => {
        const frame1 = createMockUIFrameForState({
          stateId: 'state-1',
          frameId: '3', // Note: sorting is by numeric value
          url: 'frame3.jpg',
        });
        const frame2 = createMockUIFrameForState({
          stateId: 'state-1',
          frameId: '1',
          url: 'frame1.jpg',
        });
        const frame3 = createMockUIFrameForState({
          stateId: 'state-2',
          frameId: '2',
          url: 'frame2.jpg',
        });
        
        const mockRootState = {
          videoFrames: {
            frames: {
              'state-1#chunk-1#3': frame1,
              'state-1#chunk-1#1': frame2,
              'state-2#chunk-1#2': frame3,
            },
            frameSummaries: {},
            selectedSummary: 'state-1',
          },
        } as unknown as RootState;
        
        const result = VideoFrameSelector(mockRootState);
        
        expect(result.frames).toHaveLength(2);
        expect(result.frames[0].url).toBe('frame1.jpg'); // frameId '1'
        expect(result.frames[1].url).toBe('frame3.jpg'); // frameId '3'
      });

      it('should return frame data by key', () => {
        const frame1 = createMockUIFrameForState({
          stateId: 'state-1',
          chunkId: 'chunk-1',
          frameId: 'frame-1',
          url: 'test-url.jpg',
        });
        
        const mockRootState = {
          videoFrames: {
            frames: {
              'state-1#chunk-1#frame-1': frame1,
            },
            frameSummaries: {},
            selectedSummary: 'state-1',
          },
        } as unknown as RootState;
        
        const result = VideoFrameSelector(mockRootState);
        
        expect(result.frameData('state-1#chunk-1#frame-1')).toEqual(frame1);
        expect(result.frameData('non-existent-key')).toBeNull();
      });

      it('should calculate frame summary status for chunk correctly', () => {
        // Note: The frameSummaryStatus function has a logic bug - it filters frames by chunkId only,
        // not by stateId, but summaries are filtered by stateId implicitly in the Object.values call
        const frame1 = createMockUIFrameForState({
          stateId: 'state-1',
          chunkId: 'chunk-1',
          frameId: '1',
        });
        const frame2 = createMockUIFrameForState({
          stateId: 'state-1',
          chunkId: 'chunk-1',  
          frameId: '3',
        });
        
        const summary1 = createMockUIFrameSummary({
          stateId: 'state-1',
          startFrame: '1',
          endFrame: '4', // Should overlap with both frames (1 and 3)
          summary: 'Summary for frames 1-4',
          status: StateActionStatus.COMPLETE,
        });
        
        const mockRootState = {
          videoFrames: {
            frames: {
              'state-1#chunk-1#1': frame1,
              'state-1#chunk-1#3': frame2,
            },
            frameSummaries: {
              'state-1#key-1': summary1,
            },
            selectedSummary: 'state-1',
          },
        } as unknown as RootState;
        
        const result = VideoFrameSelector(mockRootState);
        const chunkStatus = result.frameSummaryStatus('chunk-1');
        
        // The function should find the relevant summary based on frame overlap
        expect(chunkStatus.summaryUsingFrames).toBe(0); // COMPLETE status doesn't count
        expect(chunkStatus.summaries).toHaveLength(1);
        expect(chunkStatus.summaries[0].summary).toBe('Summary for frames 1-4');
      });

      it('should handle chunk with no frames', () => {
        const mockRootState = {
          videoFrames: {
            frames: {},
            frameSummaries: {},
            selectedSummary: 'state-1',
          },
        } as unknown as RootState;
        
        const result = VideoFrameSelector(mockRootState);
        const chunkStatus = result.frameSummaryStatus('chunk-1');
        
        expect(chunkStatus.summaryUsingFrames).toBe(0);
        expect(chunkStatus.summaries).toEqual([]);
        expect(chunkStatus.summaryStatus).toBe(StateActionStatus.NA);
      });
    });
  });
});
