// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useEffect, useRef } from 'react';
import { ASSETS_ENDPOINT } from '../../config';
import { useAppSelector } from '../store';
import { SearchSelector } from './searchSlice';
import { resolveSearchResultVideoUrl, resolveVideoUrl } from '../video/videoUrl';
import { ScoreDisplay } from '../../components/Search/ScoreDisplay';

export interface VideoTileProps {
  resultIndex: number; // Index in the selectedResults array
}

export const VideoTile: FC<VideoTileProps> = ({ resultIndex }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  
  // Get the search result directly from Redux
  const { selectedResults } = useAppSelector(SearchSelector);
  const searchResult = selectedResults[resultIndex];

  const { metadata, video } = searchResult || {};

  const videoUrl =
    resolveVideoUrl(video, ASSETS_ENDPOINT) ?? resolveSearchResultVideoUrl(metadata, ASSETS_ENDPOINT);

  useEffect(() => {
    const videoEl = videoRef.current;
    if (!videoEl || !videoUrl) return undefined;

    const seekTime = typeof metadata?.timestamp === 'number' ? metadata.timestamp : 0;

    // Seeking only sticks once the browser has read the container metadata, and
    // load() resets currentTime, so the seek has to be driven by the event.
    const seekToTimestamp = () => {
      if (seekTime > 0 && Number.isFinite(videoEl.duration)) {
        videoEl.currentTime = Math.min(seekTime, Math.max(videoEl.duration - 0.1, 0));
      }
    };

    videoEl.addEventListener('loadedmetadata', seekToTimestamp);
    videoEl.load();

    return () => videoEl.removeEventListener('loadedmetadata', seekToTimestamp);
  }, [videoUrl, metadata?.timestamp]);

  // If no search result at this index, don't render
  if (!searchResult) {
    console.log(`VideoTile ${resultIndex}: No search result found at index ${resultIndex}`);
    return null;
  }
  console.log(`VideoTile ${resultIndex} full searchResult:`, searchResult);

  return (
    <div className='video-tile'>
      <video ref={videoRef} controls preload='metadata'>
        <source src={videoUrl ?? ''} type='video/mp4' />
      </video>
      <div className='relevance'>
        <ScoreDisplay
          relevanceScore={metadata?.relevance_score}
          scoreBreakdown={metadata?.score_breakdown}
        />
      </div>
    </div>
  );
};
