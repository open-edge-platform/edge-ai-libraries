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
import { ClosedCaption } from '@carbon/icons-react';
import { StateActionStatus } from '../../redux/summary/summary';
import { SummarySelector } from '../../redux/summary/summarySlice';
import Markdown from 'react-markdown';
import { processMD } from '../../utils/util';

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

export const SummariesContainer: FC = () => {
  const { frameSummaries, frames, frameSummaryStatusCount } = useAppSelector(VideoFrameSelector);
  const { getSystemConfig } = useAppSelector(SummarySelector);

  const [overlap, setOverlap] = useState<number>(0);

  useEffect(() => {
    if (getSystemConfig) {
      setOverlap(getSystemConfig.frameOverlap);
    }
  }, [getSystemConfig]);

  const [modalHeading, setModalHeading] = useState<string>('');
  const [modalBody, setModalBody] = useState<string>('');
  const [showModal, setShowModal] = useState<boolean>(false);

  const detailsClickHandler = (heading: string, text: string) => {
    setModalHeading(heading);
    setModalBody(text);
    setShowModal(true);
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

        <Modal
          onRequestClose={(_) => {
            setShowModal(false);
          }}
          passiveModal
          open={showModal}
          modalHeading={modalHeading}
        >
          <ModalBody>
            <StyledMessage>
              <Markdown>{processMD(modalBody)}</Markdown>
            </StyledMessage>
          </ModalBody>
        </Modal>

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
                        `${t('Frames')}: [${summary.startFrame} : ${summary.endFrame}] - ${t('Summary')}`,
                        summary.summary,
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
