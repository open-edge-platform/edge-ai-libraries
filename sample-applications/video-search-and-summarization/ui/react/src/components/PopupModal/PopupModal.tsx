// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC } from 'react';
import { createPortal } from 'react-dom';
import { Modal } from '@carbon/react';
import styled from 'styled-components';
import { useTranslation } from 'react-i18next';

import { PopupModalProps } from './PopupModalProps.ts';

const StyledModal = styled(Modal)`
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
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--color-gray-4);
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

  & .cds--label {
    font-size: 1.1rem;
  }

  & .cds--modal-scroll-content > *:last-child {
    margin-block-end: 0;
  }
`;

const PopupModal: FC<PopupModalProps> = ({
  open = true,
  passiveModal = false,
  headingMsg,
  primaryButtonText,
  secondaryButtonText,
  size = 'sm',
  children,
  onSubmit,
  onClose,
  preventCloseOnClickOutside = false,
  primaryButtonDisabled = false,
}) => {
  const { t } = useTranslation();

  return createPortal(
    <StyledModal
      passiveModal={passiveModal}
      open={open}
      size={size}
      modalHeading={headingMsg || t('headingMsg')}
      primaryButtonText={primaryButtonText || t('confirm')}
      secondaryButtonText={secondaryButtonText}
      onRequestClose={onClose}
      onRequestSubmit={onSubmit}
      preventCloseOnClickOutside={preventCloseOnClickOutside}
      primaryButtonDisabled={primaryButtonDisabled}
    >
      {children}
    </StyledModal>,
    document.body,
  );
};

export default PopupModal;
