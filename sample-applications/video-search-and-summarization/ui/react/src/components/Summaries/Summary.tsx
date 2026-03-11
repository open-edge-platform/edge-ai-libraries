// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useEffect, useState } from 'react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { SummaryActions, SummarySelector } from '../../redux/summary/summarySlice';
import styled from 'styled-components';
import { useTranslation } from 'react-i18next';
import { StateActionStatus, SystemConfigWithMeta, UIState } from '../../redux/summary/summary';
import { AILabel, AILabelContent, IconButton, Tag } from '@carbon/react';

import { Renew, Download } from '@carbon/icons-react';
import axios from 'axios';
import ChunksContainer from './ChunksContainer';
import { socket } from '../../socket';
import { APP_URL } from '../../config';
import StatusTag, { statusClassLabel, statusClassName } from './StatusTag';
import Markdown from 'react-markdown';
import { VideoChunkActions } from '../../redux/summary/videoChunkSlice';
import { VideoFramesAction } from '../../redux/summary/videoFrameSlice';
import SummariesContainer from './SummariesContainer';
import { processMD, downloadTextFile, formatDateForFilename, sanitizeFilename } from '../../utils/util';
import { videosSelector } from '../../redux/video/videoSlice';
import { notify, NotificationSeverity } from '../Notification/notify.ts';

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
  
  section {
    display: flex;
    flex-flow: row nowrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    margin-bottom: 1rem;
    
    h3 {
      margin: 0;
      line-height: 1.5rem;
    }
    
    .left-section {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      flex: 1;
    }
  }
  
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

const DownloadButton = styled.button`
  background-color: #0066cc;
  color: #ffffff;
  border: 1px solid #0066cc;
  border-radius: 0.25rem;
  padding: 0.5rem;
  margin: 0;
  font-size: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  width: 2rem;
  height: 2rem;
  position: relative;
  transition: all 0.2s ease-in-out;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  
  &:hover {
    background-color: #0052a3;
    border-color: #0052a3;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
    transform: translateY(-1px);
  }
  
  &:hover::after {
    content: attr(data-tooltip);
    position: absolute;
    top: 50%;
    right: calc(100% + 0.5rem);
    transform: translateY(-50%);
    background-color: #333;
    color: #fff;
    padding: 0.375rem 0.75rem;
    border-radius: 0.25rem;
    font-size: 0.75rem;
    white-space: nowrap;
    z-index: 1000;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  }

  &:active {
    background-color: #003d7a;
    transform: translateY(0);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
  }

  svg {
    width: 1.125rem;
    height: 1.125rem;
    fill: #ffffff;
  }
`;
export const Summary: FC = () => {
  const { t } = useTranslation();

  const dispatch = useAppDispatch();
  const { selectedSummary, sidebarSummaries } = useAppSelector(SummarySelector);
  const { getVideoUrl, videos } = useAppSelector(videosSelector);

  const [systemConfig, setSystemConfig] = useState<SystemConfigWithMeta>();

  useEffect(() => {
    console.log(selectedSummary);
    if (selectedSummary) {
      getConfig();
      socket.emit('join', selectedSummary.stateId);

      const eventName = `summary:sync/${selectedSummary.stateId}`;

      const onSummarySync = (data: UIState) => {
        const uiState: UIState = data;
        handleSummaryData(uiState);
      };

      socket.on(eventName, onSummarySync);

      return () => {
        socket.off(eventName, onSummarySync);
      };
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

  const handleDownloadFinalSummary = () => {
    if (!selectedSummary) return;
    
    try {
      const now = new Date();
      const timestamp = now.toLocaleString();
      const dateStr = formatDateForFilename(now);
      
      // Get upload timestamp from videos list
      const video = videos.find((v: { videoId: string }) => v.videoId === selectedSummary.videoId);
      const uploadTimestamp = video?.createdAt ? new Date(video.createdAt).toLocaleString() : 'N/A';
      
      // Markdown format with proper headers
      let content = `# VIDEO SUMMARY EXPORT\n\n`;
      
      content += `## METADATA\n\n`;
      content += `| Property | Value |\n`;
      content += `|----------|-------|\n`;
      content += `| Video Title | ${selectedSummary.title} |\n`;
      content += `| Video ID | ${selectedSummary.videoId} |\n`;
      content += `| Run ID | ${selectedSummary.stateId} |\n`;
      content += `| Upload Timestamp | ${uploadTimestamp} |\n`;
      content += `| Export Timestamp | ${timestamp} |\n`;
      content += `| Total Chunks | ${selectedSummary.chunksCount} |\n`;
      content += `| Total Frames | ${selectedSummary.framesCount} |\n`;
      content += `\n`;
      
      content += `## PIPELINE CONFIGURATION\n\n`;
      content += `| Setting | Value |\n`;
      content += `|---------|-------|\n`;
      content += `| Chunk Duration | ${selectedSummary.userInputs.chunkDuration}s |\n`;
      content += `| Sampling Frame | ${selectedSummary.userInputs.samplingFrame} |\n`;
      content += `| Frame Overlap | ${selectedSummary.systemConfig.frameOverlap} |\n`;
      content += `| Multi-Frame Batch Size | ${selectedSummary.systemConfig.multiFrame} |\n`;
      if (selectedSummary.systemConfig.evamPipeline) {
        content += `| Chunking Pipeline | ${selectedSummary.systemConfig.evamPipeline} |\n`;
      }
      if (selectedSummary.systemConfig.audioModel) {
        content += `| Audio Model | ${selectedSummary.systemConfig.audioModel} |\n`;
      }
      content += `\n`;
      
      content += `## INFERENCE MODELS\n\n`;
      content += `| Model Type | Model | Device |\n`;
      content += `|------------|-------|--------|\n`;
      if (selectedSummary.inferenceConfig?.objectDetection) {
        content += `| Object Detection | ${selectedSummary.inferenceConfig.objectDetection.model} | ${selectedSummary.inferenceConfig.objectDetection.device} |\n`;
      }
      if (selectedSummary.inferenceConfig?.imageInference) {
        content += `| VLM | ${selectedSummary.inferenceConfig.imageInference.model} | ${selectedSummary.inferenceConfig.imageInference.device} |\n`;
      }
      if (selectedSummary.inferenceConfig?.textInference) {
        content += `| LLM | ${selectedSummary.inferenceConfig.textInference.model} | ${selectedSummary.inferenceConfig.textInference.device} |\n`;
      }
      content += `\n`;
      
      content += `## PROCESSING STATUS\n\n`;
      content += `| Status Type | Value |\n`;
      content += `|-------------|-------|\n`;
      content += `| Video Chunking | ${selectedSummary.chunkingStatus.toUpperCase()} |\n`;
      content += `| Frame Summaries Complete | ${selectedSummary.frameSummaryStatus.complete} |\n`;
      content += `| Frame Summaries Progress | ${selectedSummary.frameSummaryStatus.inProgress} |\n`;
      content += `| Video Summary Status | ${selectedSummary.videoSummaryStatus.toUpperCase()} |\n`;
      content += `\n`;
      
      content += `---\n\n`;
      content += `## FINAL SUMMARY\n\n`;
      content += processMD(selectedSummary.summary);
      content += `\n\n---\n\n`;
      content += `*Generated by Video Search and Summarization*\n`;
      
      // VSS_<videoName>_<runId>_<yyyyMMdd_HHmm>.md
      const videoName = sanitizeFilename(selectedSummary.title);
      const runId = sanitizeFilename(selectedSummary.stateId);
      const filename = `VSS_${videoName}_${runId}_${dateStr}.md`;
      
      downloadTextFile(content, filename);
      notify('Summary downloaded successfully', NotificationSeverity.SUCCESS, 3000);
    } catch (error) {
      console.error('Download error:', error);
      notify(
        'Download failed. Click the download button to retry.',
        NotificationSeverity.ERROR,
        5000
      );
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
            <div className="left-section">
              <h3>Summary</h3>
              <Tag size='md' type={statusClassName[selectedSummary?.videoSummaryStatus ?? StateActionStatus.NA] as any}>
                {t(statusClassLabel[selectedSummary?.videoSummaryStatus ?? StateActionStatus.NA])}
              </Tag>
            </div>
            {summaryData.summary && summaryData.summary.trim() !== '' && (
              <DownloadButton
                onClick={handleDownloadFinalSummary}
                data-tooltip={t('downloadFinalSummary')}
              >
                <Download />
              </DownloadButton>
            )}
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
