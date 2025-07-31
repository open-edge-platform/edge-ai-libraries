// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { useEffect, type FC } from 'react';

import NotificationList from './components/Notification/NotificationList.tsx';
import MainPage from './components/MainPage/MainPage.tsx';
import './utils/i18n';
import { useAppDispatch, useAppSelector } from './redux/store.ts';
import { SummaryActions, SummarySelector } from './redux/summary/summarySlice.ts';
import { socket } from './socket.ts';
import {
  InferenceConfig,
  // SummaryStreamChunk,
  UIChunk,
  UIFrame,
  UIFrameSummary,
  UIStateStatus,
} from './redux/summary/summary.ts';
import { VideoFramesAction } from './redux/summary/videoFrameSlice.ts';
import { VideoChunkActions } from './redux/summary/videoChunkSlice.ts';
import { FEATURE_MUX, FEATURE_SEARCH } from './config.ts';
import { FEATURE_STATE, FeatureMux } from './utils/constant.ts';
import { SearchActions } from './redux/search/searchSlice.ts';
import { SearchQuery } from './redux/search/search.ts';

const App: FC = () => {
  const { summaryIds } = useAppSelector(SummarySelector);

  const dispatch = useAppDispatch();

  const connectedSockets: Set<string> = new Set<string>();

  useEffect(() => {
    if (!Object.keys(FeatureMux).includes(FEATURE_MUX)) {
      throw new Error(`Feature Mux ${FEATURE_MUX} is not supported`);
    }
  });

  useEffect(() => {
    if (summaryIds.length > 0) {
      for (const summaryId of summaryIds) {
        if (!connectedSockets.has(summaryId)) {
          console.log('Connecting Socket', summaryId);

          connectedSockets.add(summaryId);

          socket.emit('join', summaryId);

          const prefix = `summary:sync/${summaryId}`;

          socket.on(`${prefix}/status`, (statusData: UIStateStatus) => {
            dispatch(
              SummaryActions.updateSummaryStatus({
                stateId: summaryId,
                ...statusData,
              }),
            );
          });
          socket.on(`${prefix}/chunks`, (chunkingData: { chunks: UIChunk[]; frames: UIFrame[] }) => {
            dispatch(
              VideoChunkActions.addChunks(
                chunkingData.chunks.map((chunk) => ({
                  ...chunk,
                  stateId: summaryId,
                })),
              ),
            );

            dispatch(
              VideoFramesAction.addFrames(
                chunkingData.frames.map((frame) => ({
                  ...frame,
                  stateId: summaryId,
                })),
              ),
            );
          });
          socket.on(`${prefix}/frameSummary`, (frameSummary: UIFrameSummary) => {
            dispatch(VideoFramesAction.updateFrameSummary(frameSummary));
          });

          socket.on(`${prefix}/inferenceConfig`, (config: InferenceConfig) => {
            dispatch(
              SummaryActions.updateInferenceConfig({
                stateId: summaryId,
                ...config,
              }),
            );
          });

          socket.on(`${prefix}/summary`, (data: { stateId: string; summary: string }) => {
            dispatch(
              SummaryActions.updateSummaryChunk({
                stateId: data.stateId,
                streamChunk: data.summary,
              }),
            );
          });

          // socket.on(
          //   `summary:sync/${summaryId}/summaryStream`,
          //   (data: SummaryStreamChunk) => {
          //     dispatch(SummaryActions.updateSummaryChunk(data));
          //   },
          // );
        }
      }
    }
    if (FEATURE_SEARCH === FEATURE_STATE.ON) {
      socket.on('search:update', (data: SearchQuery) => {
        dispatch(SearchActions.updateSearchQuery(data));
      });
    }
  }, [connectedSockets, dispatch, summaryIds]);

  return (
    <>
      <MainPage />
      <NotificationList />
    </>
  );
};

export default App;
