// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useEffect, useState } from 'react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { SummaryActions, SummarySelector } from '../../redux/summary/summarySlice';
import styled from 'styled-components';
import { useTranslation } from 'react-i18next';
import { StateActionStatus, SystemConfigWithMeta, UIState } from '../../redux/summary/summary';
import { AILabel, AILabelContent, IconButton, Tag } from '@carbon/react';

import { Renew } from '@carbon/icons-react';
import axios from 'axios';
import ChunksContainer from './ChunksContainer';
import { socket } from '../../socket';
import { APP_URL } from '../../config';
import StatusTag, { statusClassLabel, statusClassName } from './StatusTag';
import Markdown from 'react-markdown';
import { VideoChunkActions } from '../../redux/summary/videoChunkSlice';
import { VideoFramesAction } from '../../redux/summary/videoFrameSlice';
import SummariesContainer from './SummariesContainer';
import { processMD } from '../../utils/util';
import { videosSelector } from '../../redux/video/videoSlice';

export interface SummaryProps {}

const SummaryWrapper = styled.div`
  height: 100%;
  width: 100%;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 0 2rem;
  display: flex;
  flex-flow: column nowrap;
  & > * {
    width: 100%;
  }
`;

const SummaryContainer = styled.div`
  margin-top: 2rem;
  width: 100%;
  border: 1px solid var(--color-gray-4);
  padding: 1rem 1rem;
  .summary-title {
    display: flex;
    flex-flow: row nowrap;
    align-items: center;
    jsutify-content: flex-start;
  }
`;

const SummaryTitle = styled.div`
  position: sticky;
  top: 0;
  display: flex;
  flex-flow: row nowrap;
  align-items: center;
  z-index: 20;
  justify-content: flex-start;
  border: 1px solid var(--color-gray-4);
  padding: 2rem;
  height: 16rem;
  margin-top: 1rem;
  background-color: #fff;
  .video-container {
    overflow: hidden;
    height: 100%;
    .video {
      height: 100%;
    }
  }
  .info-container {
    height: 100%;
    padding: 0 1rem;
    // display: flex;
    // flex-flow: row wrap;
    // align-items: center;
    // justify-content: flex-start;
    .title-container {
      display: flex;
      flex-flow: row wrap;
      align-items: center;
      justify-content: flex-start;
      & > * {
        margin-right: 1rem;
      }
    }
    .status-container {
      display: flex;
      .status {
        padding: 0.5rem;
        border: 1px solid #000;
      }
    }
  }
`;

const NothingSelected = styled.div`
  opacity: 0.6;
  padding: 0 2rem;
`;

const Spacer = styled.span`
  flex: 1 1 auto;
`;

const StyledMessage = styled.div`
  font-size: 1rem;
  padding: 0 1rem;
  white-space: normal;
  word-break: break-word;
  width: 100%;
  line-height: 1.8;
  code {
    white-space: break-spaces;
  }
`;
export const Summary: FC = () => {
  const { t } = useTranslation();

  const dispatch = useAppDispatch();
  const { selectedSummary, sidebarSummaries } = useAppSelector(SummarySelector);
  const { getVideoUrl } = useAppSelector(videosSelector);

  const [systemConfig, setSystemConfig] = useState<SystemConfigWithMeta>();

  useEffect(() => {
    console.log(selectedSummary);
    if (selectedSummary) {
      getConfig();
      socket.emit('join', selectedSummary.stateId);

      socket.on(`summary:sync/${selectedSummary.stateId}`, (data: UIState) => {
        const uiState: UIState = data;
        handleSummaryData(uiState);
      });
    }
  }, [selectedSummary]);

  const getConfig = async () => {
    const res = await axios.get<SystemConfigWithMeta>(`${APP_URL}/app/config`);
    if (res.data) {
      setSystemConfig(res.data);
    }
  };

  const NoItemsSelected = () => {
    return (
      <NothingSelected>
        {sidebarSummaries.length > 0 && <h3>{t('selectASummaryFromSidebar')}</h3>}
        {sidebarSummaries.length === 0 && <h3>{t('noSummariesAvailable')}</h3>}
      </NothingSelected>
    );
  };

  const handleSummaryData = (data: UIState) => {
    if (selectedSummary) {
      if (selectedSummary.chunksCount !== data.chunks.length) {
        dispatch(
          VideoChunkActions.addChunks(
            data.chunks.map((curr) => ({
              ...curr,
              stateId: selectedSummary.stateId,
            })),
          ),
        );
      }

      if (data.frameSummaries.length > 0) {
        for (const frameSummary of data.frameSummaries) {
          dispatch(VideoFramesAction.updateFrameSummary(frameSummary));
        }
      }

      if (selectedSummary.chunksCount !== data.frames.length) {
        dispatch(
          VideoFramesAction.addFrames(
            data.frames.map((curr) => ({
              ...curr,
              stateId: selectedSummary.stateId,
            })),
          ),
        );
      }
    }

    dispatch(SummaryActions.updateSummaryData(data));
  };

  const refetchSummary = async (stateId: string) => {
    try {
      const api = `${APP_URL}/states/${stateId}`;

      const response = await axios.get<UIState>(api);

      if (response.data) {
        handleSummaryData(response.data);
      }
    } catch (error) {
      console.log(error);
    }
  };

  const SummaryHero = () => {
    const summaryData = selectedSummary!;
    return (
      <SummaryTitle>
        <div className='video-container'>
          <video className='video' controls>
            {getVideoUrl(summaryData.videoId) && <source src={getVideoUrl(summaryData.videoId)!}></source>}
          </video>
        </div>

        <div className='info-container'>
          <div className='title-container'>
            <h2 className='label'>{summaryData.title}</h2>

            <AILabel autoAlign>
              <AILabelContent>
                <h5 className='secondary bold'>Object Detection</h5>
                <ul>
                  <li>
                    {t('sampleRate', {
                      frames: summaryData.userInputs.samplingFrame,
                      interval: summaryData.userInputs.chunkDuration,
                      rate: (summaryData.userInputs.samplingFrame / summaryData.userInputs.chunkDuration).toFixed(2),
                    })}
                  </li>
                  {systemConfig?.meta.evamPipelines && (
                    <li>
                      {t('ChunkingPipeline', {
                        pipeline:
                          systemConfig.meta.evamPipelines.find(
                            (el) => el.value === summaryData.systemConfig.evamPipeline,
                          )?.name ?? 'N/A',
                      })}
                    </li>
                  )}
                  <li>
                    {t('aiModel', {
                      model: summaryData.inferenceConfig?.objectDetection?.model ?? 'N/A',
                    })}
                  </li>
                  <li>
                    {t('runningOn', {
                      device: summaryData.inferenceConfig?.objectDetection?.device ?? 'N/A',
                    })}
                  </li>
                </ul>
                <hr />
                <h5 className='secondary bold'>Image Inferencing</h5>
                <ul>
                  <li>
                    {t('aiModel', {
                      model: summaryData.inferenceConfig?.imageInference?.model ?? 'N/A',
                    })}
                  </li>
                  <li>
                    {t('runningOn', {
                      device: summaryData.inferenceConfig?.imageInference?.device ?? 'N/A',
                    })}
                  </li>
                  <li>
                    {t('frameOverlap', {
                      overlap: summaryData.systemConfig.frameOverlap,
                    })}{' '}
                  </li>
                  <li>
                    {t('multiFrame', {
                      multiFrame: summaryData.systemConfig.multiFrame,
                    })}{' '}
                  </li>
                </ul>
                <hr />
                <h5 className='secondary bold'>Text Inferencing</h5>
                <ul>
                  <li>
                    {t('aiModel', {
                      model: summaryData.inferenceConfig?.textInference?.model ?? 'N/A',
                    })}
                  </li>
                  <li>
                    {t('runningOn', {
                      device: summaryData.inferenceConfig?.textInference?.device ?? 'N/A',
                    })}
                  </li>
                </ul>
              </AILabelContent>
            </AILabel>
          </div>

          <div className='status-container'>
            <StatusTag action={summaryData.chunkingStatus} label={t('chunkingLabel')} />
            {summaryData.frameSummaryStatus.inProgress > 0 && (
              <StatusTag
                action={StateActionStatus.IN_PROGRESS}
                label={t('chunkingSummaryLabel')}
                count={summaryData.frameSummaryStatus.inProgress}
              />
            )}

            {summaryData.frameSummaryStatus.complete > 0 && (
              <StatusTag
                action={StateActionStatus.COMPLETE}
                label={t('chunkingSummaryLabel')}
                count={summaryData.frameSummaryStatus.complete}
              />
            )}

            <StatusTag action={summaryData.videoSummaryStatus} label={t('summaryLabel')} />
          </div>
          <div className='actions'>
            <IconButton
              label={t('SyncState')}
              align={'left'}
              size='sm'
              onClick={() => {
                refetchSummary(summaryData.stateId);
              }}
            >
              <Renew />
            </IconButton>
          </div>
        </div>

        <Spacer />
      </SummaryTitle>
    );
  };

  const VideoSummaryContainer = () => {
    const summaryData = selectedSummary!;
    return (
      <>
        <SummaryContainer>
          <section>
            <h3>Summary</h3>
            <Tag size='md' type={statusClassName[selectedSummary?.videoSummaryStatus ?? StateActionStatus.NA] as any}>
              {t(statusClassLabel[selectedSummary?.videoSummaryStatus ?? StateActionStatus.NA])}
            </Tag>
          </section>

          <StyledMessage>
            <Markdown>{processMD(summaryData.summary)}</Markdown>
          </StyledMessage>
        </SummaryContainer>
        {/* <ChunksContainer /> */}
      </>
    );
  };

  return (
    <>
      <SummaryWrapper>
        {!selectedSummary && <NoItemsSelected />}

        {selectedSummary && (
          <>
            <SummaryHero />
            <VideoSummaryContainer />
            <ChunksContainer />
            <SummariesContainer />
          </>
        )}

        {/* {selectedSummary && JSON.stringify(selectedSummary.data)} */}
      </SummaryWrapper>
    </>
  );
};

export default Summary;
