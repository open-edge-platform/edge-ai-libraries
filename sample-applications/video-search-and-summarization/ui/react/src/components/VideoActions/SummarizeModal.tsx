// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Modal } from '@carbon/react';
import { FC } from 'react';
import styled from 'styled-components';
import VideoSummarizeFlow from './VideoSummarizeFlow';
import { useTranslation } from 'react-i18next';

export interface SummarizeModalProps {
  open: boolean;
  onClose: () => void;
}

const StyledModal = styled(Modal)`
  z-index: 8000 !important;

  & .cds--modal-container {
    z-index: 8000 !important;
  }

  & .cds--modal .cds--modal-content {
    padding-block: 1rem !important;
  }

  & .cds--modal-content {
    padding-block: 1rem !important;
  }

  & .cds--modal .cds--modal-footer {
    margin-block: 1rem 2rem !important;
  }

  & .cds--modal-header__heading {
    font-size: 1.2rem;
    padding-bottom: 0.5rem;
  }

  & .cds--modal-container--sm .cds--modal-content > p,
  & .cds--modal-container--sm .cds--modal-content__regular-content {
    padding-inline-end: 0;
    width: 90%;
    margin: auto;
  }

  & .cds--modal-scroll-content {
    mask-image: none;
  }

  & .cds--modal-scroll-content > *:last-child {
    margin-block-end: 0;
  }
`;

const SummarizeModal: FC<SummarizeModalProps> = ({ open, onClose }) => {
  const { t } = useTranslation();

  return (
    <StyledModal
      open={open}
      onRequestClose={onClose}
      modalHeading={t('SummarizeVideo')}
      passiveModal={true}
    >
      <VideoSummarizeFlow onClose={onClose} />
    </StyledModal>
  );
};

export default SummarizeModal;
