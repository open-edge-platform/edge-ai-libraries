// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Modal } from '@carbon/react';
import { FC } from 'react';
import VideoEmbeddingFlow from '../MainPage/VideoEmbeddingFlow';
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
    margin-bottom: -1rem !important;
  }
  
  & .cds--modal-content {
    padding-bottom: 0 !important;
  }
`;

export interface VideoEmbeddingModalProps {
  open: boolean;
  onClose: () => void;
}

const VideoEmbeddingModal: FC<VideoEmbeddingModalProps> = ({ open, onClose }) => {
  const { t } = useTranslation();

  return (
    <StyledModal
      open={open}
      onRequestClose={onClose}
      modalHeading={t('CreateVideoEmbedding')}
      size="lg"
      className="video-embedding-modal"
      passiveModal={true}
    >
      <VideoEmbeddingFlow onClose={onClose} />
    </StyledModal>
  );
};

export default VideoEmbeddingModal;