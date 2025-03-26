// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { type FC, useEffect } from 'react';
import { IconButton } from '@carbon/react';
import styled from 'styled-components';
import { useTranslation } from 'react-i18next';

import { useAppDispatch, useAppSelector } from '../../redux/store.ts';
import {
  conversationSelector,
  setSelectedConversationId,
} from '../../redux/conversation/conversationSlice.ts';
import ConversationSideBarItem from './ConversationSideBarItem.tsx';

const SidebarContainer = styled.aside<{ disabled: boolean }>`
  display: flex;
  flex-direction: column;
  background-color: var(--color-sidebar);
  overflow: hidden;
  border-right: 1px solid var(--color-border);
  pointer-events: ${({ disabled }) => (disabled ? 'none' : 'auto')};
  opacity: ${({ disabled }) => (disabled ? 0.5 : 1)};
`;

export const Navigation = styled.div`
  padding: 1rem;
  background-color: var(--color-sidebar);
  position: sticky;
  z-index: 1;
  border-bottom: 1px solid var(--color-border);
  max-height: 3rem;
  font-size: 1.1rem;

  & h4 {
    line-height: 1;
  }
`;

const ScrollableContainer = styled.div`
  flex-grow: 1;
  overflow-y: hidden;
  padding: 5px;
  height: 80vh;
`;

export const StyledIconButton = styled(IconButton)`
  font-size: var(--icon-size);
`;

const ConversationSideBar: FC = () => {
  const { t } = useTranslation();
  const { conversations, selectedConversationId, isGenerating } =
    useAppSelector(conversationSelector);
  const dispatch = useAppDispatch();

  const sidebarList = conversations?.map((conversation) => (
    <ConversationSideBarItem
      isActive={selectedConversationId === conversation.conversationId}
      onClick={(e) => {
        e.preventDefault();
        dispatch(setSelectedConversationId(conversation.conversationId));
      }}
      key={conversation.conversationId}
      title={conversation.title}
      index={conversation.conversationId}
    />
  ));

  useEffect(() => {
    const removeTooltip = () => {
      const tooltip = document.querySelector('.cds--popover');
      if (tooltip) {
        tooltip.remove();
      }
    };

    document.addEventListener('mouseover', removeTooltip);

    return () => {
      document.removeEventListener('mouseover', removeTooltip);
    };
  }, []);

  return (
    <SidebarContainer
      disabled={isGenerating}
      data-testid='conversation-sidebar-wrapper'
    >
      {sidebarList.length ? (
        <>
          <Navigation>{t('chatHistory')}</Navigation>
          <ScrollableContainer>{sidebarList}</ScrollableContainer>
        </>
      ) : null}
    </SidebarContainer>
  );
};

export default ConversationSideBar;
