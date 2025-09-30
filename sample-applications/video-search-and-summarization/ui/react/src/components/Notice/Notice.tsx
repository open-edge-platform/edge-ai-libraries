// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { FC } from 'react';
import styled from 'styled-components';
import { useTranslation } from 'react-i18next';

import { useDisclosure } from '../../hooks/useDisclosure.ts';
import { NoticeKind, NoticeProps } from './NoticeProps.ts';
import { StyledIconButton } from '../Summaries/SummarySideBar.tsx';

const NoticeContainer = styled.div<{ kind: string }>`
  padding: 0 1rem;
  color: var(--color-black);
  grid-column: 1 / -1;

  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  text-align: center;
  background-color: ${({ kind }) => `var(--color-${kind})`};
  transition:
    transform 0.5s ease-in-out,
    opacity 0.5s ease-in-out;
`;

const Notice: FC<NoticeProps> = ({
  message,
  kind = NoticeKind.DEFAULT,
  isNoticeVisible,
  setIsNoticeVisible,
}) => {
  const { t } = useTranslation();
  const [isOpen, { close }] = useDisclosure(true);

  const handleClose = () => {
    close();
    setIsNoticeVisible(false);
  };

  return (
    <>
      {message && isOpen && isNoticeVisible && (
        <NoticeContainer kind={kind} data-testid='notice-container'>
          {message}
          <StyledIconButton
            label={t('close')}
            kind='tertiary'
            align='left'
            onClick={handleClose}
            data-testid='close-button'
          >
            &times;
          </StyledIconButton>
        </NoticeContainer>
      )}
    </>
  );
};

export default Notice;
