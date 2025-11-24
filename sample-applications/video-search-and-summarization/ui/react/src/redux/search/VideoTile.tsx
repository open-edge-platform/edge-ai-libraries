// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { ASSETS_ENDPOINT } from '../../config';
import { useAppSelector } from '../store';
import { SearchSelector } from './searchSlice';

export interface VideoTileProps {
  resultIndex: number; // Index in the selectedResults array
}

export const VideoTile: FC<VideoTileProps> = ({ resultIndex }) => {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  
  // Get the search result directly from Redux
  const { selectedResults } = useAppSelector(SearchSelector);
  const searchResult = selectedResults[resultIndex];

  const { metadata, video } = searchResult || {};

  const getVideoUrl = () => {
    if (video?.dataStore) {
      return `${ASSETS_ENDPOINT}/${video.dataStore.bucket}/${video.url}`;
    }
    return null;
  };

  const videoUrl = getVideoUrl();

  useEffect(() => {
    if (videoRef.current && metadata?.timestamp && typeof metadata.timestamp === 'number') {
      videoRef.current.currentTime = metadata.timestamp;
    }
  }, [metadata?.timestamp]);

  // Force video reload when URL changes
  useEffect(() => {
    if (videoRef.current && videoUrl) {
      videoRef.current.load();
    }
  }, [videoUrl]);

  // If no search result at this index, don't render
  if (!searchResult) {
    console.log(`VideoTile ${resultIndex}: No search result found at index ${resultIndex}`);
    return null;
  }
  console.log(`VideoTile ${resultIndex} full searchResult:`, searchResult);

  return (
    <div className='video-tile'>
      <video ref={videoRef} controls>
        <source src={videoUrl ?? ''} />
      </video>
      <div className='relevance'>
        {t('RelevanceScore')}: {metadata?.relevance_score != null ? metadata.relevance_score.toFixed(3) : 'N/A'}
      </div>
    </div>
  );
};
