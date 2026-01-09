// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useEffect, useState } from 'react';
import styled from 'styled-components';
import { useAppSelector } from '../../redux/store';
import { VideoFrameSelector } from '../../redux/summary/videoFrameSlice';
import { useHorizontalScroll } from '../../utils/horizontalScroller';
import { useTranslation } from 'react-i18next';
import { CountStatusEmp, statusClassName } from './StatusTag';
import { IconButton, Modal, ModalBody } from '@carbon/react';
import { ClosedCaption, Download } from '@carbon/icons-react';
import { StateActionStatus } from '../../redux/summary/summary';
import { SummarySelector } from '../../redux/summary/summarySlice';
import Markdown from 'react-markdown';
import { processMD, downloadTextFile, formatDateForFilename, sanitizeFilename } from '../../utils/util';
import { notify, NotificationSeverity } from '../Notification/notify.ts';
import { videosSelector } from '../../redux/video/videoSlice';

const SummaryWrapper = styled.section`
  @keyframes fadeInOut {
    0% {
      opacity: 0.2;
    }
    50% {
      opacity: 1;
    }
    100% {
      opacity: 0.2;
    }
  }

  @mixin statusColors {
    &.gray {
      background-color: var(--color-default);
    }
    &.purple {
      background-color: var(--color-warning);
    }

    &.blue {
      background-color: var(--color-info);
      animation: fadeInOut 2s;
      animation-iteration-count: infinite;
    }
    &.green {
      background-color: var(--color-success);
    }
  }

  display: flex;
  margin-top: 2rem;
  width: 100%;
  border: 1px solid var(--color-gray-4);
  padding: 1rem 1rem;
  flex-flow: column nowrap;
  .frames {
    display: grid;
    overflow-x: auto;
    gap: 5px;
    padding: 2rem;
    position: relative;
    &::before {
      position: absolute;
      top: 0;
      left: 1rem;
      content: 'Frames >';
      border-bottom: 1px solid #000;
    }
    &::after {
      position: absolute;
      top: 1rem;
      left: 1rem;
      content: '< Overlaps';
      transform: translate(-60%, 180%) rotate(-90deg);
      border-bottom: 1px solid #000;
    }
    .frame-summary {
      padding: 8px;
      border-radius: 8px;
      display: flex;
      flex-flow: row nowrap;
      align-items: center;
      justify-content: flex-start;
      &.gray {
        background-color: var(--color-default);
      }
      &.purple {
        background-color: var(--color-warning);
      }

      &.blue {
        background-color: var(--color-info);
        animation: fadeInOut 2s;
        animation-iteration-count: infinite;
      }
      &.green {
        background-color: var(--color-success);
      }
    }
  }
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

export const SummariesContainer: FC = () => {
  const { frameSummaries, frames, frameSummaryStatusCount } = useAppSelector(VideoFrameSelector);
  const { getSystemConfig, selectedSummary } = useAppSelector(SummarySelector);
  const { videos } = useAppSelector(videosSelector);

  const [overlap, setOverlap] = useState<number>(0);

  useEffect(() => {
    if (getSystemConfig) {
      setOverlap(getSystemConfig.frameOverlap);
    }
  }, [getSystemConfig]);

  const [modalHeading, setModalHeading] = useState<string>('');
  const [modalBody, setModalBody] = useState<string>('');
  const [showModal, setShowModal] = useState<boolean>(false);
  const [currentFrameRange, setCurrentFrameRange] = useState<{ start: string; end: string } | null>(null);

  const detailsClickHandler = (text: string, startFrame: string, endFrame: string) => {
    setModalHeading('Chunk Summary');
    setModalBody(text);
    setCurrentFrameRange({ start: startFrame, end: endFrame });
    setShowModal(true);
  };

  const handleDownloadFrameSummary = () => {
    if (!currentFrameRange || !modalBody || !selectedSummary) return;
    
    try {
      const now = new Date();
      const timestamp = now.toLocaleString();
      const dateStr = formatDateForFilename(now);
      
      // Get upload timestamp from videos list
      const video = videos.find((v: { videoId: string }) => v.videoId === selectedSummary.videoId);
      const uploadTimestamp = video?.createdAt ? new Date(video.createdAt).toLocaleString() : 'N/A';
      
      // Markdown format
      let content = `# FRAME SUMMARY EXPORT\n\n`;
      
      content += `## METADATA\n\n`;
      content += `| Property | Value |\n`;
      content += `|----------|-------|\n`;
      content += `| Video Title | ${selectedSummary.title} |\n`;
      content += `| Video ID | ${selectedSummary.videoId} |\n`;
      content += `| Run ID | ${selectedSummary.stateId} |\n`;
      content += `| Frame Range | [${currentFrameRange.start}:${currentFrameRange.end}] |\n`;
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
      content += `## FRAME SUMMARY\n\n`;
      content += processMD(modalBody);
      content += `\n\n---\n\n`;
      content += `*Generated by Video Search and Summarization*\n`;
      
      // VSS_<videoName>_<runId>_<yyyyMMdd_HHmm>.md
      const videoName = sanitizeFilename(selectedSummary.title);
      const runId = sanitizeFilename(selectedSummary.stateId);
      const filename = `VSS_${videoName}_${runId}_frames_${currentFrameRange.start}_to_${currentFrameRange.end}_${dateStr}.md`;
      
      downloadTextFile(content, filename);
      notify('Frame summary downloaded successfully', NotificationSeverity.SUCCESS, 3000);
    } catch (error) {
      console.error('Download error:', error);
      notify(
        'Download failed. Click the download button to retry.',
        NotificationSeverity.ERROR,
        5000
      );
    }
  };

  const { t } = useTranslation();

  const scrollerRef = useHorizontalScroll();

  return (
    <>
      <SummaryWrapper>
        <section className='sectionHeader'>
          <h3>{t('FrameSummaries')}</h3>
          <CountStatusEmp label='' status={frameSummaryStatusCount} />
        </section>

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
              onClick={handleDownloadFrameSummary}
              data-tooltip={t('downloadFrameSummary')}
            >
              <Download />
            </DownloadButton>
          </div>
          <ModalBody>
            {currentFrameRange && (
              <StyledMessage>
                <h4>
                  {t('Frames')}: [{currentFrameRange.start} : {currentFrameRange.end}]
                </h4>
                <Markdown>{processMD(modalBody)}</Markdown>
              </StyledMessage>
            )}
          </ModalBody>
        </StyledModal>

        <div
          className='frames'
          ref={scrollerRef}
          style={{
            gridTemplateColumns: `repeat(${frames.length - 1}, minmax(50px, 1fr))`,
            gridTemplateRows: `1fr repeat(${overlap + 1}, 1fr)`,
          }}
        >
          {frames.map((frame) => (
            <div className='frame' key={`frame_header_` + frame.frameId}>
              {frame.frameId}
            </div>
          ))}

          {frameSummaries.map((summary, index) => (
            <div
              className={'frame-summary ' + statusClassName[summary.status]}
              key={`frame_summary_` + summary.frameKey}
              style={{
                gridArea: `${2 + (index % (overlap + 1))} / ${summary.startFrame} / span 1 / span ${+summary.endFrame - +summary.startFrame + 1}`,
              }}
            >
              <span className='heading'>
                {t('Frames')}: [{summary.startFrame} : {summary.endFrame}]
              </span>
              <span className='spacer'></span>
              <span className='actions'>
                {summary.status === StateActionStatus.COMPLETE && summary.summary && (
                  <IconButton
                    label='Summary'
                    kind='ghost'
                    onClick={() =>
                      detailsClickHandler(
                        summary.summary,
                        summary.startFrame,
                        summary.endFrame,
                      )
                    }
                  >
                    <ClosedCaption />
                  </IconButton>
                )}

                {summary.status !== StateActionStatus.COMPLETE && (
                  <IconButton label='' disabled kind='ghost'>
                    {/* <ClosedCaption /> */}
                  </IconButton>
                )}
              </span>
            </div>
          ))}
        </div>

        {/* {JSON.stringify(frameSummaries)} */}
      </SummaryWrapper>
    </>
  );
};

export default SummariesContainer;
