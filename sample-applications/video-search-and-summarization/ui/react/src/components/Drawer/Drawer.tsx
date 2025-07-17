// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { FC, ReactNode } from 'react';
import styled from 'styled-components';
import { useTranslation } from 'react-i18next';
import { Navigation } from '../Summaries/SummarySideBar';
import {
  IconButton,
  Toggletip,
  ToggletipButton,
  ToggletipContent,
} from '@carbon/react';
import { Close, Information } from '@carbon/icons-react';

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

const CodePara = styled.p`
  font-style: italic;
`;

const Drawer: FC<DrawerProps> = ({ title, isOpen, close, children }) => {
  const { t } = useTranslation();

  const ffmpegStreamableCmd =
    'ffmpeg -i <input mp4 video> -c copy -map 0 -movflags +faststart <output mp4 video>';

  return (
    <>
      <Overlay $isOpen={isOpen} onClick={close} />
      <DrawerWrapper $isOpen={isOpen}>
        <DrawerNavigation>
          <h6>{title || t('drawerTitle')}</h6>
          <span className='spacer'></span>
          <Toggletip autoAlign>
            <ToggletipButton>
              <Information />
            </ToggletipButton>

            <ToggletipContent>
              <p>{t('OnlyMp4')}</p>
              <p>{t('HelpText')}</p>
              <CodePara>
                <strong>{ffmpegStreamableCmd}</strong>
              </CodePara>
            </ToggletipContent>
          </Toggletip>
          <IconButton label='Close' kind='ghost' onClick={close}>
            <Close />
          </IconButton>
        </DrawerNavigation>
        {children}
      </DrawerWrapper>
    </>
  );
};

export default Drawer;
