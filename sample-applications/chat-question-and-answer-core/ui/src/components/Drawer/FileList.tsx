// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState, type FC } from 'react';
import styled from 'styled-components';
import { useTranslation } from 'react-i18next';
import { Document } from '@carbon/icons-react';
import {
  Tab,
  TabList,
  TabPanels,
  Tabs,
  TabPanel,
  Tag,
  Button,
} from '@carbon/react';

import { useAppSelector } from '../../redux/store.ts';
import { conversationSelector } from '../../redux/conversation/conversationSlice.ts';
import FileLinkManager from './FileLinkManager.tsx';
import { Icon } from '../Navbar/Navbar.tsx';
import DataSource from './DataSource.tsx';

interface FileListProps {
  closeDrawer: () => void;
  isOpen: boolean;
}

const StyledMessage = styled.div`
  margin: auto;
  margin-top: 1rem;
  color: var(--color-dark-0);
  line-height: 1.3;
`;

export const CountTag = styled(Tag)`
  position: absolute;
  top: -1rem;
  right: -1.5rem;
  font-size: 0.6rem;
  min-inline-size: 1rem;
`;

export const TitleContainer = styled.div`
  display: flex;
  align-items: center;

  .mr-8 {
    margin-right: 8px;
  }
`;

const FlexContainerWithCount = styled(TitleContainer)`
  position: relative;
  font-size: 1.1rem;
  font-weight: 400;
`;

const StyledTabPanel = styled(TabPanel)`
  background-color: var(--color-white) !important;
`;

const StickyTabs = styled(TabList)`
  position: sticky;
  top: 0;
  background-color: var(--color-white);
  z-index: 1;
`;

const FullWidthButton = styled(Button)`
  min-width: 100%;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  justify-content: center;
  padding-block: 0;
  padding-inline: 0;
  font-size: 1.1rem;
`;

export const SmallPara = styled.p`
  font-size: 1rem;
  margin-bottom: 1rem;
`;

const FileList: FC<FileListProps> = ({ closeDrawer, isOpen }) => {
  const { t } = useTranslation();
  const { files = [] } = useAppSelector(conversationSelector) || {};
  const [showUploadForm, setShowUploadForm] = useState<boolean>(false);

  const handleButtonClick = () => {
    setShowUploadForm(true);
  };

  useEffect(() => {
    if (!isOpen) {
      setShowUploadForm(false);
    }
  }, [isOpen]);

  return (
    <Tabs data-testid='file-list-tabs'>
      <StickyTabs aria-label={t('documents')} contained>
        <Tab>
          <FlexContainerWithCount>
            <Document className='mr-8 mt-2p' size='1.2rem' />
            {t('files')}
            <CountTag>{files.length}</CountTag>
          </FlexContainerWithCount>
        </Tab>
      </StickyTabs>

      <TabPanels>
        <StyledTabPanel>
          {showUploadForm ? (
            <>
              <SmallPara>{t('uploadFileDescription')}</SmallPara>
              <DataSource close={closeDrawer} />
            </>
          ) : (
            <FullWidthButton kind='primary' onClick={handleButtonClick}>
              <Icon>+</Icon>
              {t('addNewFile')}
            </FullWidthButton>
          )}

          {files.length === 0 ? (
            <StyledMessage>{t('noFilesFound')}</StyledMessage>
          ) : (
            <FileLinkManager
              showField={showUploadForm}
              closeDrawer={closeDrawer}
            />
          )}
        </StyledTabPanel>
      </TabPanels>
    </Tabs>
  );
};

export default FileList;
