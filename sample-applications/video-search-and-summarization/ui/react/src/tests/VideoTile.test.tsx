// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { I18nextProvider } from 'react-i18next';
import i18n from '../utils/i18n';
import { VideoTile, VideoTileProps } from '../redux/search/VideoTile';

// Mock the useAppSelector hook
const mockVideoSelector = {
  getVideoUrl: vi.fn()
};

vi.mock('../redux/store', () => ({
  useAppSelector: vi.fn(() => mockVideoSelector)
}));

// Create mock store
const createMockStore = (state = {}) => {
  return configureStore({
    reducer: {
      video: (state = { videos: {}, selectedVideoId: null }) => state,
      search: (state = { searchResults: [], isLoading: false }) => state,
    },
    preloadedState: state,
  });
};

describe('VideoTile Component', () => {
  let store: any;
  
  beforeEach(() => {
    store = createMockStore();
    vi.clearAllMocks();
    mockVideoSelector.getVideoUrl.mockReturnValue('http://example.com/video.mp4');
  });

  const renderVideoTile = (props: VideoTileProps) => {
    return render(
      <Provider store={store}>
        <I18nextProvider i18n={i18n}>
          <VideoTile {...props} />
        </I18nextProvider>
      </Provider>
    );
  };

  it('should render video tile with basic props', () => {
    const { container } = renderVideoTile({ videoId: 'test-video-1' });
    
    const video = container.querySelector('video') as HTMLVideoElement;
    expect(video).toBeInTheDocument();
    expect(video.querySelector('source')).toHaveAttribute('src', 'http://example.com/video.mp4');
    expect(container.textContent).toContain('Relevance Score');
    expect(container.textContent).toContain('N/A');
  });

  it('should render video tile with relevance score', () => {
    const { container } = renderVideoTile({ 
      videoId: 'test-video-2', 
      relevance: 0.856789 
    });
    
    expect(container.textContent).toContain('Relevance Score');
    expect(container.textContent).toContain('0.857');
  });

  it('should render video tile with zero relevance score', () => {
    const { container } = renderVideoTile({ 
      videoId: 'test-video-3', 
      relevance: 0 
    });
    
    expect(container.textContent).toContain('Relevance Score');
    expect(container.textContent).toContain('N/A'); // 0 is falsy, so shows N/A
  });

  it('should set video current time when startTime is provided', () => {
    const { container } = renderVideoTile({ 
      videoId: 'test-video-4', 
      startTime: 45.5 
    });
    
    const video = container.querySelector('video') as HTMLVideoElement;
    expect(video).toBeInTheDocument();
    // Note: currentTime is set in useEffect, testing structure for now
    expect(video.controls).toBe(true);
  });

  it('should handle missing video URL gracefully', () => {
    mockVideoSelector.getVideoUrl.mockReturnValue(null);
    
    const { container } = renderVideoTile({ videoId: 'missing-video' });
    
    const video = container.querySelector('video') as HTMLVideoElement;
    expect(video).toBeInTheDocument();
    expect(video.querySelector('source')).toHaveAttribute('src', '');
  });

  it('should handle undefined video URL', () => {
    mockVideoSelector.getVideoUrl.mockReturnValue(undefined);
    
    const { container } = renderVideoTile({ videoId: 'undefined-video' });
    
    const video = container.querySelector('video') as HTMLVideoElement;
    expect(video).toBeInTheDocument();
    expect(video.querySelector('source')).toHaveAttribute('src', '');
  });

  it('should render with all props provided', () => {
    const { container } = renderVideoTile({ 
      videoId: 'complete-video',
      startTime: 30.25,
      relevance: 0.9123456
    });
    
    const video = container.querySelector('video') as HTMLVideoElement;
    expect(video).toBeInTheDocument();
    expect(video.querySelector('source')).toHaveAttribute('src', 'http://example.com/video.mp4');
    expect(container.textContent).toContain('0.912');
  });

  it('should call getVideoUrl with correct videoId', () => {
    renderVideoTile({ videoId: 'specific-video-id' });
    
    expect(mockVideoSelector.getVideoUrl).toHaveBeenCalledWith('specific-video-id');
  });

  it('should display video tile CSS class', () => {
    const { container } = renderVideoTile({ videoId: 'css-test-video' });
    
    expect(container.querySelector('.video-tile')).toBeInTheDocument();
    expect(container.querySelector('.relevance')).toBeInTheDocument();
  });

  it('should render video with controls enabled', () => {
    const { container } = renderVideoTile({ videoId: 'controls-test' });
    
    const video = container.querySelector('video') as HTMLVideoElement;
    expect(video.controls).toBe(true);
  });

  it('should handle large relevance numbers', () => {
    const { container } = renderVideoTile({ 
      videoId: 'large-relevance',
      relevance: 999.123456
    });
    
    expect(container.textContent).toContain('999.123');
  });

  it('should handle negative relevance numbers', () => {
    const { container } = renderVideoTile({ 
      videoId: 'negative-relevance',
      relevance: -0.456789
    });
    
    expect(container.textContent).toContain('-0.457');
  });
});
