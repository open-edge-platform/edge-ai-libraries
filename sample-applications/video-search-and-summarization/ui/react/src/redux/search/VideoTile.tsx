import { FC, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppSelector } from '../store';
import { videosSelector } from '../video/videoSlice';

export interface VideoTileProps {
  videoId: string;
  startTime?: number;
  relevance?: number;
}

export const VideoTile: FC<VideoTileProps> = ({ videoId, startTime, relevance }) => {
  const { t } = useTranslation();

  const videoRef = useRef<HTMLVideoElement>(null);

  const { getVideoUrl } = useAppSelector(videosSelector);

  useEffect(() => {
    if (videoRef.current && startTime && typeof startTime === 'number') {
      videoRef.current.currentTime = startTime;
    }
  }, [startTime]);

  return (
    <div className='video-tile'>
      <video ref={videoRef} controls>
        <source src={getVideoUrl(videoId) ?? ''} />
      </video>
      <div className='relevance'>
        {t('RelevanceScore')}: {relevance ? relevance.toFixed(3) : 'N/A'}
      </div>
    </div>
  );
};
