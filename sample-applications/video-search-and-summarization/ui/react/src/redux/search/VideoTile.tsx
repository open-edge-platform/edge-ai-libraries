// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useRef } from 'react';
import { ASSETS_ENDPOINT } from '../../config';
import { useAppSelector } from '../store';
import { SearchSelector } from './searchSlice';
import { resolveSearchResultVideoUrl, resolveVideoUrl } from '../video/videoUrl';
import { useSeekableVideo } from '../video/useSeekableVideo';
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

  const seekTime = typeof metadata?.timestamp === 'number' ? metadata.timestamp : 0;
  useSeekableVideo(videoRef, videoUrl, seekTime);

  // If no search result at this index, don't render
  if (!searchResult) {
    return null;
  }

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
