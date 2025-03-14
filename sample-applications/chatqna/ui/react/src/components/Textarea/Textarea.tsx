// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  type ChangeEvent,
  type FC,
  type KeyboardEventHandler,
  useEffect,
  useState,
  useRef,
  KeyboardEvent,
  Dispatch,
  SetStateAction,
} from 'react';
import { IconButton, TextArea } from '@carbon/react';
import { SendFilled } from '@carbon/icons-react';
import styled from 'styled-components';
import { useTranslation } from 'react-i18next';

import { Message, MessageRole } from '../../redux/conversation/conversation.ts';
import { fetchModelName, getCurrentTimeStamp } from '../../utils/util.ts';
import {
  conversationSelector,
  doConversation,
} from '../../redux/conversation/conversationSlice.ts';
import { NotificationSeverity, notify } from '../Notification/notify.ts';
import { useAppSelector } from '../../redux/store.ts';

export const StyledTextArea = styled(TextArea)<{ $borderRadius?: number }>`
  textarea {
    resize: none;
    overflow: hidden;
    font-size: 16px;
    border-radius: ${({ $borderRadius = 0 }) => $borderRadius}px;
  }

  textarea:focus,
  textarea:active {
    overflow-y: auto;
  }

  textarea::placeholder {
    font-size: 1.05rem;
  }
`;

const TextareaWrapper = styled.div`
  display: flex;
  align-items: center;
  gap: 1rem;
`;

const EnterButton = styled(IconButton)`
  justify-self: end;
  height: 2rem;
`;

const StyledHeader = styled.h3`
  text-align: center;
  color: var(--color-gray-2);
`;

interface TextareaProps {
  rows?: number;
  setModelName: Dispatch<SetStateAction<string>>;
}

const Textarea: FC<TextareaProps> = ({ rows = 1, setModelName }) => {
  const { t } = useTranslation();
  const [prompt, setPrompt] = useState<string>('');

  const [isPromptValid, setIsPromptValid] = useState<boolean>(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { isGenerating, files = [] } =
    useAppSelector(conversationSelector) || {};

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [textareaRef]);

  const handleChange = (event: ChangeEvent<HTMLTextAreaElement>): void => {
    const value = event.target.value;
    setPrompt(value);
    setIsPromptValid(value.trim().length > 0);
  };

  const setLLMModel = async () => {
    const response = await fetchModelName();
    if (response.status === 200) {
      setModelName(response.llmModel);
    } else {
      notify(
        response.message || t('llmModelNotSet'),
        NotificationSeverity.ERROR,
      );
    }
  };

  const handleSubmit = () => {
    if (!prompt.trim()) {
      setPrompt('');
      setIsPromptValid(false);
      return;
    }
    const userPrompt: Message = {
      role: MessageRole.User,
      content: prompt.trim(),
      time: getCurrentTimeStamp(),
      conversationId: '',
    };

    setLLMModel();

    doConversation({
      userPrompt,
    });
    setPrompt('');
    setIsPromptValid(false);
  };

  const handleKeyDown: KeyboardEventHandler<HTMLTextAreaElement> = (
    event: KeyboardEvent<HTMLTextAreaElement>,
  ) => {
    if (isGenerating && event.key === 'Enter') {
      event.preventDefault();
      notify(t('showNotificationWhileStreaming'), NotificationSeverity.WARNING);
      return;
    }
    if (!prompt && event.key === 'Enter') {
      event.preventDefault();
      return;
    }
    if (!event.shiftKey && event.key === 'Enter') {
      event.preventDefault();
      handleSubmit();
    }
  };

  const placeholderText: string =
    t('modelIntro') + (files.length ? t('withContext') : t('withoutContext'));

  return (
    <>
      <StyledHeader data-testid='textarea-intro'>{t('intro')}</StyledHeader>
      <TextareaWrapper data-testid='textarea-wrapper'>
        <StyledTextArea
          ref={textareaRef}
          labelText=''
          placeholder={placeholderText}
          value={prompt}
          onKeyDown={handleKeyDown}
          onChange={handleChange}
          rows={rows}
          data-testid='prompt-textarea'
        />
        <EnterButton
          label={prompt.trim() === '' ? t('emptyMessage') : t('submit')}
          onClick={handleSubmit}
          align='left'
          kind='primary'
          disabled={!isPromptValid || isGenerating}
          data-testid='submit-prompt'
        >
          <SendFilled />
        </EnterButton>
      </TextareaWrapper>
    </>
  );
};

export default Textarea;
