// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { FC, ReactNode } from 'react';
import styled from 'styled-components';
import { useTranslation } from 'react-i18next';

import { Navigation } from '../Conversation/ConversationSideBar.tsx';

interface DrawerProps {
  title?: ReactNode;
  isOpen: boolean;
  close: () => void;
  children?: ReactNode;
}

const DrawerWrapper = styled.div<{ $isOpen: boolean }>`
  position: fixed;
  top: 0;
  right: 0;
  height: 100%;
  width: 450px;
  background-color: var(--color-white);
  background-color: var(--color-white);
  box-shadow: -2px 0 5px var(--color-data-source-bs);
  transform: ${({ $isOpen }) =>
    $isOpen ? 'translateX(0)' : 'translateX(100%)'};
  transition: transform 0.3s ease-in-out;
  z-index: 1000;
  display: flex;
  flex-direction: column;
`;

const CloseButton = styled.button`
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;

  &:hover,
  &:visited,
  &:link,
  &:active {
    color: var(--color-info);
  }
`;

const Overlay = styled.div<{ $isOpen: boolean }>`
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: var(--color-data-source-bg);
  opacity: ${({ $isOpen }) => ($isOpen ? '1' : '0')};
  visibility: ${({ $isOpen }) => ($isOpen ? 'visible' : 'hidden')};
  transition:
    opacity 0.3s ease-in-out,
    visibility 0.3s ease-in-out;
  z-index: 999;
`;

const DrawerNavigation = styled(Navigation)`
  display: flex;
  align-items: center;
  justify-content: space-between;
`;

const Drawer: FC<DrawerProps> = ({ title, isOpen, close, children }) => {
  const { t } = useTranslation();
  return (
    <>
      <Overlay $isOpen={isOpen} onClick={close} data-testid='overlay' />
      <DrawerWrapper $isOpen={isOpen} data-testid='drawer-wrapper'>
        <DrawerNavigation>
          <h4>{title || t('drawerTitle')}</h4>
          <CloseButton onClick={close}>&times;</CloseButton>
        </DrawerNavigation>
        {children}
      </DrawerWrapper>
    </>
  );
};

export default Drawer;
