// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState, type FC } from 'react';
import styled from 'styled-components';
import { useTranslation } from 'react-i18next';

import { useAppDispatch, useAppSelector } from '../../redux/store.ts';
import {
  conversationSelector,
  fetchInitialFiles,
} from '../../redux/conversation/conversationSlice.ts';
import { MessageRole } from '../../redux/conversation/conversation.ts';
import ConversationMessage from './ConversationMessage.tsx';
import { Navigation } from './ConversationSideBar.tsx';
import Textarea from '../Textarea/Textarea.tsx';
import { capitalize } from '../../utils/util.ts';

const Container = styled.main`
  display: flex;
  flex-direction: column;
`;

const Info = styled.div`
  display: flex;
  justify-content: center;
  flex-direction: column;
  width: 95%;
  flex-grow: 1;
  margin: auto;
  gap: 5px;

  & p {
    color: var(--color-gray-2);
    font-size: 4rem;
    text-align: center;
  }
`;

const ScrollableContainer = styled.div`
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  height: 60vh;
  overflow-y: auto;
  scroll-behavior: smooth;
  gap: 1rem;

  & > *:first-child {
    margin-top: 8px;
  }
`;

export const StyledModelWrapper = styled.div<{ $hasMargin?: boolean }>`
  display: flex;
  justify-content: flex-end;
  margin: ${({ $hasMargin = false }) => ($hasMargin ? '0 1rem 1rem 0' : '0')};
`;

const StyledModel = styled.a`
  font-weight: bold;
  color: var(--color-primary-blue);
  font-family: Arial, sans-serif;
  font-size: 1rem;
  font-style: italic;
  margin: 1rem 1rem 0 0;
`;

const Conversation: FC = () => {
  const { t } = useTranslation();
  const [modelName, setModelName] = useState<string>('');

  const dispatch = useAppDispatch();
  const { conversations, onGoingResult, selectedConversationId, isGenerating } =
    useAppSelector(conversationSelector);

  const selectedConversation = conversations.find(
    (conversation) => conversation.conversationId === selectedConversationId,
  );

  const selectedConversationTitle = selectedConversation?.title;
  const { responseStatus = false } = selectedConversation || {};

  const scrollViewport = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    scrollViewport.current?.scrollTo({
      top: scrollViewport.current.scrollHeight,
      behavior: 'smooth',
    });
  };

  useEffect(() => {
    scrollToBottom();
  }, [onGoingResult, selectedConversation?.messages]);

  useEffect(() => {
    const fetchFiles = async () => {
      try {
        await dispatch(fetchInitialFiles()).unwrap();
      } catch {
        console.log('Failed to fetch files');
      }
    };

    fetchFiles();
  }, [dispatch, t]);

  const LLM_MODEL_URL: string = `https://huggingface.co/${modelName}`;

  return (
    <Container data-testid='conversation-container'>
      {selectedConversationTitle ? (
        <Navigation>
          <h4>{capitalize(selectedConversationTitle)}</h4>
        </Navigation>
      ) : null}

      {!selectedConversationId ? (
        <Info>
          <Textarea rows={2} setModelName={setModelName} />
        </Info>
      ) : (
        <ScrollableContainer ref={scrollViewport}>
          {selectedConversation?.messages.map((message, index) => (
            <ConversationMessage
              key={index}
              date={message.time * 1000}
              human={message.role === MessageRole.User}
              message={message.content}
            />
          ))}
          {isGenerating && (
            <ConversationMessage
              date={Date.now()}
              human={false}
              message={onGoingResult}
              isGenerating={isGenerating}
            />
          )}
          {responseStatus && (
            <StyledModelWrapper $hasMargin={true}>
              <StyledModel href={LLM_MODEL_URL} target='_blank'>
                {modelName}
              </StyledModel>
            </StyledModelWrapper>
          )}
        </ScrollableContainer>
      )}
    </Container>
  );
};

export default Conversation;
