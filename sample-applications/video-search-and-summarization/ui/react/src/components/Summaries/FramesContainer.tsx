// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC } from 'react';
import { useAppSelector } from '../../redux/store';
import { VideoFrameSelector } from '../../redux/summary/videoFrameSlice';

import { ASSETS_ENDPOINT } from '../../config';
export interface FrameContainerProps {
  frameKey: string;
}
export const FrameContainer: FC<FrameContainerProps> = ({ frameKey }) => {
  const { frameData } = useAppSelector(VideoFrameSelector);

  return (
    <>
      <div className='frame'>
        <div className='frame-title'>
          <span>{frameData(frameKey).videoTimeStamp?.toFixed(2) + 's'}</span>

          <span className='spacer'></span>
        </div>
        <div className='status'></div>
        <div className='frame-content'>
          {frameData(frameKey).url && (
            <img
              className='frame-image'
              src={ASSETS_ENDPOINT + frameData(frameKey).url}
            />
          )}
          <span className='frame-info'>{frameData(frameKey).frameId}</span>
        </div>
      </div>
    </>
  );
};

export interface FramesContainerProps {
  chunkId: string;
}
export const FramesContainer: FC<FramesContainerProps> = ({ chunkId }) => {
  const { frameKeys } = useAppSelector(VideoFrameSelector);

  return (
    <>
      <div className='frames'>
        {frameKeys(chunkId).map((frameKey) => (
          <FrameContainer frameKey={frameKey} key={frameKey} />
        ))}
      </div>
    </>
  );
};

export default FramesContainer;
