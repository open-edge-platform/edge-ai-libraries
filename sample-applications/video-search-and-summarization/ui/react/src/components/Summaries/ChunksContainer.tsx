// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useEffect, useState } from 'react';
import { useHorizontalScroll } from '../../utils/horizontalScroller';

import './ChunksContainer.scss';
import { useTranslation } from 'react-i18next';
import { useAppSelector } from '../../redux/store';
import { VideoChunkSelector } from '../../redux/summary/videoChunkSlice';
import { SummarySelector } from '../../redux/summary/summarySlice';
import { videosSelector } from '../../redux/video/videoSlice';
import FramesContainer from './FramesContainer';
import { VideoFrameSelector } from '../../redux/summary/videoFrameSlice';
import {
  ChunkSummaryStatusFromFrames,
  CountStatus,
  StateActionStatus,
  SummaryStatusWithFrames,
  UIChunkForState,
} from '../../redux/summary/summary';
import { Modal, ModalBody, Tooltip } from '@carbon/react';
import styled from 'styled-components';
import Markdown from 'react-markdown';
import { processMD, downloadTextFile, formatDateForFilename, sanitizeFilename } from '../../utils/util';
import { ClosedCaption, Information, Download } from '@carbon/icons-react';
import { getStatusByPriority, StatusIndicator } from './StatusTag';
import { notify, NotificationSeverity } from '../Notification/notify.ts';

export interface ChunksContainerProps {}

interface ChunkContainer {
  chunkKey: string;
}

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

const StyledModal = styled(Modal)`
  .cds--modal-header {
    display: flex;
    align-items: center;
    padding-right: 3rem;
  }
  
  .download-button-wrapper {
    position: absolute;
    right: 3rem;
    top: 1rem;
    z-index: 1;
  }
`;
export const ChunkContainer: FC<ChunkContainer> = ({ chunkKey }) => {
  const { chunkData } = useAppSelector(VideoChunkSelector);
  const { frames, frameSummaries } = useAppSelector(VideoFrameSelector);
  const { t } = useTranslation();

  const [modalHeading, setModalHeading] = useState<string>('');
  const [modalBody, setModalBody] = useState<SummaryStatusWithFrames[]>([]);
  const [showModal, setShowModal] = useState<boolean>(false);

  const detailsClickHandler = (heading: string, text: SummaryStatusWithFrames[]) => {
    setModalHeading(heading);
    setModalBody(text);
    setShowModal(true);
  };

  const { selectedSummary } = useAppSelector(SummarySelector);
  const { videos } = useAppSelector(videosSelector);

  const handleDownloadChunkSummary = () => {
    if (!uiChunkData || modalBody.length === 0 || !selectedSummary) return;
    
    try {
      const now = new Date();
      const timestamp = now.toLocaleString();
      const dateStr = formatDateForFilename(now);
      
      // Get upload timestamp from videos list
      const video = videos.find((v: { videoId: string }) => v.videoId === selectedSummary.videoId);
      const uploadTimestamp = video?.createdAt ? new Date(video.createdAt).toLocaleString() : 'N/A';
      
      // Markdown format
      let content = `# VIDEO CHUNK SUMMARY EXPORT\n\n`;
      
      content += `## METADATA\n\n`;
      content += `| Property | Value |\n`;
      content += `|----------|-------|\n`;
      content += `| Video Title | ${selectedSummary.title} |\n`;
      content += `| Video ID | ${selectedSummary.videoId} |\n`;
      content += `| Run ID | ${selectedSummary.stateId} |\n`;
      content += `| Chunk ID | ${uiChunkData.chunkId} |\n`;
      content += `| Duration | ${uiChunkData.duration.from.toFixed(2)}s - ${uiChunkData.duration.to === -1 ? 'End of Video' : uiChunkData.duration.to.toFixed(2) + 's'} |\n`;
      content += `| Upload Timestamp | ${uploadTimestamp} |\n`;
      content += `| Export Timestamp | ${timestamp} |\n`;
      content += `| Total Chunks | ${selectedSummary.chunksCount} |\n`;
      content += `| Total Frames | ${selectedSummary.framesCount} |\n`;
      content += `\n`;
      
      content += `## CONFIGURATION\n\n`;
      content += `| Setting | Value |\n`;
      content += `|---------|-------|\n`;
      content += `| Chunk Duration | ${selectedSummary.userInputs.chunkDuration}s |\n`;
      content += `| Sampling Frame | ${selectedSummary.userInputs.samplingFrame} |\n`;
      content += `| Frame Overlap | ${selectedSummary.systemConfig.frameOverlap} |\n`;
      content += `| Multi-Frame Batch | ${selectedSummary.systemConfig.multiFrame} |\n`;
      if (selectedSummary.inferenceConfig?.imageInference?.model) {
        content += `| VLM Model | ${selectedSummary.inferenceConfig.imageInference.model} |\n`;
      }
      content += `\n`;
      
      content += `---\n\n`;
      content += `## CHUNK SUMMARIES\n\n`;
      
      modalBody.forEach((summ, idx) => {
        content += `### Summary ${idx + 1} - Frames [${summ.frames[0]}:${summ.frames[summ.frames.length - 1]}]\n\n`;
        content += processMD(summ.summary);
        content += `\n\n`;
      });
      
      content += `---\n\n`;
      content += `*Generated by Video Search and Summarization*\n`;
      
      // VSS_<videoName>_<runId>_<yyyyMMdd_HHmm>.md
      const videoName = sanitizeFilename(selectedSummary.title);
      const runId = sanitizeFilename(selectedSummary.stateId);
      const filename = `VSS_${videoName}_${runId}_chunk${uiChunkData.chunkId}_${dateStr}.md`;
      
      downloadTextFile(content, filename);
      notify('Chunk summary downloaded successfully', NotificationSeverity.SUCCESS, 3000);
    } catch (error) {
      console.error('Download error:', error);
      notify(
        'Download failed. Click the download button to retry.',
        NotificationSeverity.ERROR,
        5000
      );
    }
  };
  const [summaryStatus, setSummaryStatus] = useState<ChunkSummaryStatusFromFrames>(() => ({
    summaries: [],
    summaryUsingFrames: 0,
    summaryStatus: StateActionStatus.NA,
    hasEmbeddings: false,
  }));

  const [uiChunkData, setUIChunkData] = useState<UIChunkForState | null>(null);

  useEffect(() => {
    if (chunkData && chunkData[chunkKey]) {
      setUIChunkData(chunkData[chunkKey]);
    }
  }, [chunkData]);

  useEffect(() => {
    if (uiChunkData && frames.length > 0 && frameSummaries.length > 0) {
      const response: ChunkSummaryStatusFromFrames = {
        summaryUsingFrames: 0,
        summaries: [],
        summaryStatus: StateActionStatus.NA,
        hasEmbeddings: false,
      };

      const chunkFrames = frames
        .filter((el) => el.chunkId === uiChunkData.chunkId)
        .sort((a, b) => +a.frameId - +b.frameId);

      if (chunkFrames.length > 0) {
        const lastFrame = chunkFrames[chunkFrames.length - 1];

        const relevantSumms = frameSummaries.filter(
          (el) => +el.endFrame >= +lastFrame.frameId && +el.endFrame <= +lastFrame.frameId,
        );

        for (const summ of relevantSumms) {
          const statusCount: CountStatus = {
            complete: 0,
            inProgress: 0,
            na: 0,
            ready: 0,
          };

          statusCount[summ.status] += 1;
          response.summaryUsingFrames += 1;
          response.summaryStatus = getStatusByPriority(statusCount);
          if (summ.summary) {
            response.summaries.push({
              summary: summ.summary,
              status: summ.status,
              frames: summ.frames,
            });
          }
        }

        response.hasEmbeddings = frameSummaries.some((el) => el.embeddingsCreated);
      }

      setSummaryStatus(response);
    }
  }, [frames, frameSummaries, uiChunkData]);

  return (
    <>
      <div className='chunk'>
        <StyledModal
          onRequestClose={(_) => {
            setShowModal(false);
          }}
          open={showModal}
          modalHeading={modalHeading}
          passiveModal
        >
          <div className="download-button-wrapper">
            <DownloadButton
              onClick={handleDownloadChunkSummary}
              data-tooltip={t('downloadChunkSummary')}
            >
              <Download />
            </DownloadButton>
          </div>
          <ModalBody>
            {modalBody.map((summ) => (
              <StyledMessage key={`${summ.frames[0]}-${summ.frames[summ.frames.length - 1]}`}>
                <h4>
                  {t('SummaryForframes', {
                    start: summ.frames[0],
                    end: summ.frames[summ.frames.length - 1],
                  })}
                </h4>
                <Markdown>{processMD(summ.summary)}</Markdown>
              </StyledMessage>
            ))}
          </ModalBody>
        </StyledModal>
        <div className='chunk-header'>
          <span className='chunk-name'>
            {t('ChunkPrefix') + ' ' + uiChunkData?.chunkId}
            <span className='spacer'></span>

            {summaryStatus.summaryUsingFrames > 0 && (
              <StatusIndicator
                label={t('SummaryInProgress', {
                  count: summaryStatus.summaryUsingFrames,
                })}
                action={summaryStatus.summaryStatus}
              />
            )}

            {summaryStatus.hasEmbeddings && (
              <Tooltip label={t('EmbeddingsCreated')} autoAlign>
                <Information />
              </Tooltip>
            )}
            {summaryStatus.summaries.length > 0 && (
              <Tooltip
                label={t('showSummaries')}
                autoAlign
                onClick={() => {
                  detailsClickHandler(
                    t('chunkSummaryHeading', {
                      chunkId: uiChunkData?.chunkId,
                    }),
                    summaryStatus.summaries,
                  );
                }}
              >
                <ClosedCaption />
              </Tooltip>
              // <IconButton
              //   label={t('showSummaries')}
              //   kind='ghost'
              //   onClick={() => {
              //     detailsClickHandler(
              //       t('chunkSummaryHeading', {
              //         chunkId: uiChunkData?.chunkId,
              //       }),
              //       summaryStatus.summaries,
              //     );
              //   }}
              // >
              // </IconButton>
            )}
          </span>
          {uiChunkData?.duration && (
            <div className='chunk-duration'>
              <span>{uiChunkData.duration.from.toFixed(2) + 's'} </span>
              <span className='spacer'></span>
              <span>{uiChunkData.duration.to == -1 ? t('endOfVideo') : uiChunkData.duration.to.toFixed(2) + 's'}</span>
            </div>
          )}
        </div>
        {uiChunkData && <FramesContainer chunkId={uiChunkData.chunkId} />}
      </div>
    </>
  );
};

export const ChunksContainer: FC = () => {
  const scrollRef = useHorizontalScroll();

  const { t } = useTranslation();

  const { chunkKeys } = useAppSelector(VideoChunkSelector);

  return (
    <>
      <section className='chunks-wrapper'>
        <h3>{t('Chunks')}</h3>

        <div className='chunks-container' ref={scrollRef}>
          {chunkKeys.map((chunkKey) => (
            <ChunkContainer chunkKey={chunkKey} key={chunkKey} />
          ))}
        </div>
      </section>
    </>
  );
};

export default ChunksContainer;
