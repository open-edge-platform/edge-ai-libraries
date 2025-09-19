// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { configureStore } from '@reduxjs/toolkit';
import axios from 'axios';
import { 
  VideoActions, 
  VideoReducers, 
  videosLoad,
  videosSelector 
} from '../redux/video/videoSlice';
import { 
  VideosState,
  Video, 
  VideosRO,
  VideoDatastoreInfo
} from '../redux/video/video';
import { StateActionStatus } from '../redux/summary/summary';
import { RootState } from '../redux/store';
import { APP_URL, ASSETS_ENDPOINT } from '../config';

// Mock axios
vi.mock('axios');
const mockedAxios = vi.mocked(axios);

// Console.log is used in the selector, mock it to avoid test noise
beforeEach(() => {
  vi.spyOn(console, 'log').mockImplementation(() => {});
  vi.clearAllMocks();
});

// Mock store setup
const createMockStore = (initialState?: Partial<VideosState>) => {
  return configureStore({
    reducer: {
      videos: VideoReducers,
    },
    preloadedState: {
      videos: {
        videos: [],
        status: StateActionStatus.READY,
        ...initialState,
      },
    },
  });
};

// Mock data factories
const createMockVideo = (overrides?: Partial<Video>): Video => ({
  dbId: 1,
  videoId: 'video-123',
  name: 'Test Video',
  url: 'videos/test-video.mp4',
  tags: ['test', 'sample'],
  createdAt: '2024-01-01T10:00:00Z',
  updatedAt: '2024-01-01T10:00:00Z',
  summaries: ['summary-1'],
  textEmbeddings: true,
  videoEmbeddings: false,
  dataStore: {
    bucket: 'test-bucket',
    objectName: 'test-object',
    fileName: 'test-video.mp4',
  },
  ...overrides,
});

const createMockVideoDatastore = (overrides?: Partial<VideoDatastoreInfo>): VideoDatastoreInfo => ({
  bucket: 'default-bucket',
  objectName: 'default-object',
  fileName: 'default-file.mp4',
  ...overrides,
});

describe('VideoSlice', () => {
  describe('Initial State', () => {
    it('should have correct initial state', () => {
      const store = createMockStore();
      const state = store.getState().videos;
      
      expect(state.videos).toEqual([]);
      expect(state.status).toBe(StateActionStatus.READY);
    });
  });

  describe('Reducers', () => {
    describe('addVideo', () => {
      it('should add a video to the state', () => {
        const store = createMockStore();
        const mockVideo = createMockVideo();
        
        store.dispatch(VideoActions.addVideo(mockVideo));
        
        const state = store.getState().videos;
        expect(state.videos).toHaveLength(1);
        expect(state.videos[0]).toEqual(mockVideo);
      });

      it('should add multiple videos', () => {
        const store = createMockStore();
        const video1 = createMockVideo({ videoId: 'video-1', name: 'Video 1' });
        const video2 = createMockVideo({ videoId: 'video-2', name: 'Video 2' });
        
        store.dispatch(VideoActions.addVideo(video1));
        store.dispatch(VideoActions.addVideo(video2));
        
        const state = store.getState().videos;
        expect(state.videos).toHaveLength(2);
        expect(state.videos[0].videoId).toBe('video-1');
        expect(state.videos[1].videoId).toBe('video-2');
      });

      it('should maintain existing videos when adding new one', () => {
        const existingVideo = createMockVideo({ videoId: 'existing', name: 'Existing' });
        const store = createMockStore({
          videos: [existingVideo],
        });
        
        const newVideo = createMockVideo({ videoId: 'new', name: 'New Video' });
        store.dispatch(VideoActions.addVideo(newVideo));
        
        const state = store.getState().videos;
        expect(state.videos).toHaveLength(2);
        expect(state.videos[0].videoId).toBe('existing');
        expect(state.videos[1].videoId).toBe('new');
      });
    });

    describe('removeVideo', () => {
      it('should remove a video by videoId', () => {
        const video1 = createMockVideo({ videoId: 'video-1' });
        const video2 = createMockVideo({ videoId: 'video-2' });
        const store = createMockStore({
          videos: [video1, video2],
        });
        
        store.dispatch(VideoActions.removeVideo({ videoId: 'video-1' }));
        
        const state = store.getState().videos;
        expect(state.videos).toHaveLength(1);
        expect(state.videos[0].videoId).toBe('video-2');
      });

      it('should handle removing non-existent video', () => {
        const video1 = createMockVideo({ videoId: 'video-1' });
        const store = createMockStore({
          videos: [video1],
        });
        
        store.dispatch(VideoActions.removeVideo({ videoId: 'non-existent' }));
        
        const state = store.getState().videos;
        expect(state.videos).toHaveLength(1);
        expect(state.videos[0].videoId).toBe('video-1');
      });

      it('should handle empty videos array', () => {
        const store = createMockStore();
        
        store.dispatch(VideoActions.removeVideo({ videoId: 'any-id' }));
        
        const state = store.getState().videos;
        expect(state.videos).toHaveLength(0);
      });

      it('should remove all matching videos', () => {
        const video1 = createMockVideo({ videoId: 'video-1' });
        const video2 = createMockVideo({ videoId: 'video-2' });
        const video3 = createMockVideo({ videoId: 'video-1' }); // Duplicate ID
        const store = createMockStore({
          videos: [video1, video2, video3],
        });
        
        store.dispatch(VideoActions.removeVideo({ videoId: 'video-1' }));
        
        const state = store.getState().videos;
        expect(state.videos).toHaveLength(1);
        expect(state.videos[0].videoId).toBe('video-2');
      });
    });

    describe('updateVideo', () => {
      it('should update existing video', () => {
        const existingVideo = createMockVideo({ 
          videoId: 'video-1', 
          name: 'Original Name',
          tags: ['old', 'tags']
        });
        const store = createMockStore({
          videos: [existingVideo],
        });
        
        const updatePayload = { 
          videoId: 'video-1', 
          name: 'Updated Name',
          tags: ['new', 'tags']
        };
        store.dispatch(VideoActions.updateVideo(updatePayload));
        
        const state = store.getState().videos;
        expect(state.videos).toHaveLength(1);
        expect(state.videos[0].name).toBe('Updated Name');
        expect(state.videos[0].tags).toEqual(['new', 'tags']);
        expect(state.videos[0].videoId).toBe('video-1'); // Should preserve other fields
      });

      it('should partially update video fields', () => {
        const existingVideo = createMockVideo({ 
          videoId: 'video-1', 
          name: 'Original Name',
          tags: ['original']
        });
        const store = createMockStore({
          videos: [existingVideo],
        });
        
        const updatePayload = { 
          videoId: 'video-1', 
          name: 'Updated Name'
          // tags not provided, should preserve original
        };
        store.dispatch(VideoActions.updateVideo(updatePayload));
        
        const state = store.getState().videos;
        expect(state.videos[0].name).toBe('Updated Name');
        expect(state.videos[0].tags).toEqual(['original']); // Should preserve original tags
      });

      it('should not update if video not found', () => {
        const existingVideo = createMockVideo({ videoId: 'existing-video' });
        const store = createMockStore({
          videos: [existingVideo],
        });
        
        const updatePayload = { 
          videoId: 'non-existent', 
          name: 'Updated Name'
        };
        store.dispatch(VideoActions.updateVideo(updatePayload));
        
        const state = store.getState().videos;
        expect(state.videos).toHaveLength(1);
        expect(state.videos[0].name).toBe('Test Video'); // Original name unchanged
      });

      it('should update correct video when multiple exist', () => {
        const video1 = createMockVideo({ videoId: 'video-1', name: 'Video 1' });
        const video2 = createMockVideo({ videoId: 'video-2', name: 'Video 2' });
        const video3 = createMockVideo({ videoId: 'video-3', name: 'Video 3' });
        const store = createMockStore({
          videos: [video1, video2, video3],
        });
        
        const updatePayload = { 
          videoId: 'video-2', 
          name: 'Updated Video 2'
        };
        store.dispatch(VideoActions.updateVideo(updatePayload));
        
        const state = store.getState().videos;
        expect(state.videos[0].name).toBe('Video 1'); // Unchanged
        expect(state.videos[1].name).toBe('Updated Video 2'); // Updated
        expect(state.videos[2].name).toBe('Video 3'); // Unchanged
      });
    });
  });

  describe('Async Thunks', () => {
    describe('videosLoad', () => {
      it('should handle successful video loading', async () => {
        const mockVideosData: VideosRO = {
          videos: [
            createMockVideo({ videoId: 'video-1', name: 'Loaded Video 1' }),
            createMockVideo({ videoId: 'video-2', name: 'Loaded Video 2' }),
          ],
        };
        
        (mockedAxios.get as any).mockResolvedValue({ data: mockVideosData });
        
        const store = createMockStore();
        await store.dispatch(videosLoad());
        
        const state = store.getState().videos;
        expect(state.status).toBe(StateActionStatus.READY);
        expect(state.videos).toHaveLength(2);
        expect(state.videos[0].name).toBe('Loaded Video 1');
        expect(state.videos[1].name).toBe('Loaded Video 2');
        
        expect(mockedAxios.get).toHaveBeenCalledWith(`${APP_URL}/videos`);
      });

      it('should handle loading state correctly', async () => {
        const mockVideosData: VideosRO = { videos: [] };
        (mockedAxios.get as any).mockResolvedValue({ data: mockVideosData });
        
        const store = createMockStore();
        
        // Check initial state
        expect(store.getState().videos.status).toBe(StateActionStatus.READY);
        
        const loadPromise = store.dispatch(videosLoad());
        
        // Check pending state
        expect(store.getState().videos.status).toBe(StateActionStatus.IN_PROGRESS);
        
        await loadPromise;
        
        // Check fulfilled state
        expect(store.getState().videos.status).toBe(StateActionStatus.READY);
      });

      it('should handle loading failure', async () => {
        (mockedAxios.get as any).mockRejectedValue(new Error('Network error'));
        
        const store = createMockStore({
          videos: [createMockVideo()], // Existing video
        });
        
        await store.dispatch(videosLoad());
        
        const state = store.getState().videos;
        expect(state.status).toBe(StateActionStatus.READY);
        expect(state.videos).toHaveLength(1); // Should preserve existing videos
      });

      it('should replace existing videos on successful load', async () => {
        const existingVideo = createMockVideo({ videoId: 'existing' });
        const store = createMockStore({
          videos: [existingVideo],
        });
        
        const mockVideosData: VideosRO = {
          videos: [
            createMockVideo({ videoId: 'new-1' }),
            createMockVideo({ videoId: 'new-2' }),
          ],
        };
        
        (mockedAxios.get as any).mockResolvedValue({ data: mockVideosData });
        
        await store.dispatch(videosLoad());
        
        const state = store.getState().videos;
        expect(state.videos).toHaveLength(2);
        expect(state.videos.find(v => v.videoId === 'existing')).toBeUndefined();
        expect(state.videos.find(v => v.videoId === 'new-1')).toBeDefined();
        expect(state.videos.find(v => v.videoId === 'new-2')).toBeDefined();
      });

      it('should handle empty videos response', async () => {
        const mockVideosData: VideosRO = { videos: [] };
        (mockedAxios.get as any).mockResolvedValue({ data: mockVideosData });
        
        const store = createMockStore();
        await store.dispatch(videosLoad());
        
        const state = store.getState().videos;
        expect(state.status).toBe(StateActionStatus.READY);
        expect(state.videos).toEqual([]);
      });
    });
  });

  describe('videosSelector', () => {
    describe('getVideo', () => {
      it('should find video by videoId', () => {
        const video1 = createMockVideo({ videoId: 'video-1', name: 'Video 1' });
        const video2 = createMockVideo({ videoId: 'video-2', name: 'Video 2' });
        
        const mockRootState = {
          videos: {
            videos: [video1, video2],
            status: StateActionStatus.READY,
          },
        } as unknown as RootState;
        
        const result = videosSelector(mockRootState);
        
        expect(result.getVideo('video-1')).toEqual(video1);
        expect(result.getVideo('video-2')).toEqual(video2);
        expect(result.getVideo('non-existent')).toBeUndefined();
      });

      it('should handle empty videos array', () => {
        const mockRootState = {
          videos: {
            videos: [],
            status: StateActionStatus.READY,
          },
        } as unknown as RootState;
        
        const result = videosSelector(mockRootState);
        
        expect(result.getVideo('any-id')).toBeUndefined();
      });
    });

    describe('getVideoUrl', () => {
      it('should construct video URL with dataStore', () => {
        const videoWithDatastore = createMockVideo({
          videoId: 'video-1',
          url: 'path/to/video.mp4',
          dataStore: createMockVideoDatastore({
            bucket: 'my-bucket',
          }),
        });
        
        const mockRootState = {
          videos: {
            videos: [videoWithDatastore],
            status: StateActionStatus.READY,
          },
        } as unknown as RootState;
        
        const result = videosSelector(mockRootState);
        
        expect(result.getVideoUrl('video-1')).toBe(
          `${ASSETS_ENDPOINT}/my-bucket/path/to/video.mp4`
        );
      });

      it('should return null for video without dataStore', () => {
        const videoWithoutDatastore = createMockVideo({
          videoId: 'video-1',
          dataStore: undefined,
        });
        
        const mockRootState = {
          videos: {
            videos: [videoWithoutDatastore],
            status: StateActionStatus.READY,
          },
        } as unknown as RootState;
        
        const result = videosSelector(mockRootState);
        
        expect(result.getVideoUrl('video-1')).toBeNull();
      });

      it('should return null for non-existent video', () => {
        const mockRootState = {
          videos: {
            videos: [],
            status: StateActionStatus.READY,
          },
        } as unknown as RootState;
        
        const result = videosSelector(mockRootState);
        
        expect(result.getVideoUrl('non-existent')).toBeNull();
      });

      it('should handle video with null dataStore', () => {
        const videoWithNullDatastore = createMockVideo({
          videoId: 'video-1',
          dataStore: null as any,
        });
        
        const mockRootState = {
          videos: {
            videos: [videoWithNullDatastore],
            status: StateActionStatus.READY,
          },
        } as unknown as RootState;
        
        const result = videosSelector(mockRootState);
        
        expect(result.getVideoUrl('video-1')).toBeNull();
      });

      it('should handle different bucket and url combinations', () => {
        const video1 = createMockVideo({
          videoId: 'video-1',
          url: 'folder/subfolder/video1.mp4',
          dataStore: createMockVideoDatastore({
            bucket: 'production-bucket',
          }),
        });
        
        const video2 = createMockVideo({
          videoId: 'video-2',
          url: 'video2.mp4',
          dataStore: createMockVideoDatastore({
            bucket: 'test-bucket',
          }),
        });
        
        const mockRootState = {
          videos: {
            videos: [video1, video2],
            status: StateActionStatus.READY,
          },
        } as unknown as RootState;
        
        const result = videosSelector(mockRootState);
        
        expect(result.getVideoUrl('video-1')).toBe(
          `${ASSETS_ENDPOINT}/production-bucket/folder/subfolder/video1.mp4`
        );
        expect(result.getVideoUrl('video-2')).toBe(
          `${ASSETS_ENDPOINT}/test-bucket/video2.mp4`
        );
      });
    });
  });
});
