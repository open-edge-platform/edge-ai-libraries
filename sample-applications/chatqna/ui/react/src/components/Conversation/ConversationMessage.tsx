// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { FC } from 'react';
import styled, { keyframes } from 'styled-components';
import { formatDistanceToNow } from 'date-fns';
import { useTranslation } from 'react-i18next';

interface ConversationMessageProps {
  message: string;
  human: boolean;
  date: number;
  isGenerating?: boolean;
}

const ConversationMessageContainer = styled.div<{ $human: boolean }>`
  display: flex;
  width: 100%;
  flex-direction: column;
  background-color: ${({ $human }) =>
    $human ? 'var(--color-message-container)' : ''};
  padding: 0.5rem 0;
`;

const IconContainer = styled.span`
  font-size: 1rem;
  margin: 0.5rem;
  display: flex;
  align-items: center;
  font-weight: bold;
`;

const StyledMessage = styled.div`
  font-size: 1rem;
  padding: 0 1rem;
  white-space: pre-wrap;
  word-break: break-word;
  width: 90%;
  margin: auto;
  line-height: 1.8;
`;

const Timestamp = styled.span`
  font-size: 0.75rem;
  color: var(--color-date);
`;

const blink = keyframes`
  0% { opacity: 1; }
  50% { opacity: 0; }
  100% { opacity: 1; }
`;

const Circle = styled.span`
  display: inline-block;
  width: 8px;
  height: 8px;
  background-color: black;
  margin-left: 2px;
  border-radius: 50%;
  animation: ${blink} 1s step-end infinite;
`;

export const FlexDiv = styled.div<{ $gap?: number }>`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: ${({ $gap = 0 }) => $gap}rem;
`;

const MessageWrapper = styled.div`
  width: 90%;
  margin: auto;
`;

const ConversationMessage: FC<ConversationMessageProps> = ({
  human,
  message,
  date,
  isGenerating = false,
}) => {
  const { t } = useTranslation();

  return (
    <ConversationMessageContainer $human={!human}>
      <MessageWrapper>
        <FlexDiv>
          <IconContainer>{human ? t('question') : t('response')}</IconContainer>
          <Timestamp>
            {formatDistanceToNow(date, { addSuffix: true })}
          </Timestamp>
        </FlexDiv>
        <StyledMessage>
          {message}
          {isGenerating && <Circle data-testid='circle' />}
        </StyledMessage>
      </MessageWrapper>
    </ConversationMessageContainer>
  );
};

export default ConversationMessage;
