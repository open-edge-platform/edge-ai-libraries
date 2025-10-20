// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useEffect, useState } from 'react';
import { useHorizontalScroll } from '../../utils/horizontalScroller';

import './ChunksContainer.scss';
import { useTranslation } from 'react-i18next';
import { useAppSelector } from '../../redux/store';
import { VideoChunkSelector } from '../../redux/summary/videoChunkSlice';
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
import { processMD } from '../../utils/util';
import { ClosedCaption, Information } from '@carbon/icons-react';
import { getStatusByPriority, StatusIndicator } from './StatusTag';

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
        <Modal
          onRequestClose={(_) => {
            setShowModal(false);
          }}
          passiveModal
          open={showModal}
          modalHeading={modalHeading}
        >
          <ModalBody>
            {modalBody.map((summ) => (
              <StyledMessage>
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
        </Modal>
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
