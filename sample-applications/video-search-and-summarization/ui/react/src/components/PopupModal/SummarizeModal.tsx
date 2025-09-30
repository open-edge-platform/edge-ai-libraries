// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Modal } from '@carbon/react';
import { FC } from 'react';
import VideoSummarizeFlow from '../MainPage/VideoSummarizeFlow';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';

const StyledModal = styled(Modal)`
  & .cds--modal-scroll-content {
    mask-image: none !important;
  }
  
  & .cds--modal-footer {
    box-shadow: none !important;
    border-top: none !important;
    margin-left: -1rem !important;
    margin-right: -1rem !important;
    margin-bottom: 1rem !important;
  }
  
  & .cds--modal-content {
    padding-bottom: 0 !important;
    max-height: 85vh !important;
    overflow: hidden !important;
  }
  
  & .cds--modal-container {
    max-height: 90vh !important;
    width: 90vw !important;
    max-width: 1000px !important;
  }
`;

export interface SummarizeModalProps {
  open: boolean;
  onClose: () => void;
}

const SummarizeModal: FC<SummarizeModalProps> = ({ open, onClose }) => {
  const { t } = useTranslation();

  return (
    <StyledModal
      open={open}
      onRequestClose={onClose}
      modalHeading={t('SummarizeVideo')}
      size="lg"
      className="summarize-modal"
      passiveModal={true}
    >
      <VideoSummarizeFlow onClose={onClose} />
    </StyledModal>
  );
};

export default SummarizeModal;
