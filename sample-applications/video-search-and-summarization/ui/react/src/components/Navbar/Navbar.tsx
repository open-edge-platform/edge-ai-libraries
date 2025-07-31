// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState, type FC } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import { Button } from '@carbon/react';
import { Video } from '@carbon/icons-react';

import Drawer from '../Drawer/Drawer.tsx';
import { useDisclosure } from '../../hooks/useDisclosure.ts';
import VideoUpload from '../Drawer/VideoUpload.tsx';
import PromptInputModal from '../Modals/PromptInputModal.tsx';
import { FEATURE_SEARCH, FEATURE_SUMMARY } from '../../config.ts';
import { VideoUploadSearch } from '../Drawer/VideoUploadSearch.tsx';
import { useAppDispatch } from '../../redux/store.ts';
import { videosLoad } from '../../redux/video/videoSlice.ts';
import { SearchModal } from '../PopupModal/SearchModal.tsx';
import { FEATURE_STATE } from '../../utils/constant.ts';
import { LoadTags } from '../../redux/search/searchSlice.ts';

const StyledDiv = styled.div`
  display: flex;
  align-items: center;
  width: 100%;
  justify-content: space-between;
  color: var(--color-white);
  background-color: var(--color-info);
  padding: 0.5rem;
  flex-grow: 0;
  position: sticky;
  top: 0;
  z-index: 1;
  // height: 3rem;
`;

const Logo = styled.p`
  font-size: 1.4rem;
`;

export const Icon = styled.div`
  margin-right: 0.5rem;
  padding-bottom: 1px;
  font-weight: 100;
  font-size: 1.5rem;
`;

export const TitleContainer = styled.div`
  display: flex;
  align-items: center;
  font-size: 1.2rem;
  font-weight: 400;

  .mr-8 {
    margin-right: 8px;
  }
`;

const Navbar: FC = () => {
  const { t } = useTranslation();

  const [isDrawerOpen, { open: openDrawer, close: closeDrawer }] = useDisclosure(false);
  const dispatch = useAppDispatch();

  useEffect(() => {
    dispatch(videosLoad());
  }, []);

  const getBrandName = () => {
    const hasSearch = FEATURE_SEARCH == FEATURE_STATE.ON;
    const hasSummary = FEATURE_SUMMARY == FEATURE_STATE.ON;

    if (hasSearch && hasSummary) {
      return t('VSSBrand');
    } else if (hasSearch) {
      return t('VSearchBrand');
    } else {
      return t('VSummBrand');
    }
  };

  const getVideoUploadAction = () => {
    const hasSearch = FEATURE_SEARCH == FEATURE_STATE.ON;
    const hasSummary = FEATURE_SUMMARY == FEATURE_STATE.ON;
    if (hasSearch && hasSummary) {
      return t('SummarizeVideo');
    } else if (hasSearch) {
      return t('CreateVideoEmbedding');
    } else {
      return t('SummarizeVideo');
    }
  };

  const getVideoUploadDrawer = () => {
    const hasSearch = FEATURE_SEARCH == FEATURE_STATE.ON;
    const hasSummary = FEATURE_SUMMARY == FEATURE_STATE.ON;
    dispatch(LoadTags());
    if (hasSearch && hasSummary) {
      return <VideoUpload closeDrawer={closeDrawer} isOpen={isDrawerOpen} />;
    } else if (hasSearch) {
      return <VideoUploadSearch closeDrawer={closeDrawer} isOpen={isDrawerOpen} />;
    } else {
      return <VideoUpload closeDrawer={closeDrawer} isOpen={isDrawerOpen} />;
    }
  };

  const [showSearchModal, setShowSearchModal] = useState<boolean>(false);

  const closeSearchModal = () => {
    setShowSearchModal(false);
  };

  return (
    <>
      {FEATURE_SUMMARY == FEATURE_STATE.ON && <PromptInputModal />}

      {FEATURE_SEARCH == FEATURE_STATE.ON && <SearchModal showModal={showSearchModal} closeModal={closeSearchModal} />}

      <StyledDiv>
        {/* <Logo>{t('VideoSummary')}</Logo> */}
        <Logo>{getBrandName()}</Logo>
        <span className='spacer'></span>

        {FEATURE_SEARCH == FEATURE_STATE.ON && (
          <Button
            kind='primary'
            disabled={false}
            onClick={() => {
              dispatch(LoadTags());
              setShowSearchModal(true);
            }}
          >
            {t('SearchVideo')}
          </Button>
        )}

        <Button kind='primary' onClick={openDrawer} disabled={false}>
          {getVideoUploadAction()}
        </Button>
      </StyledDiv>

      <Drawer
        isOpen={isDrawerOpen}
        close={closeDrawer}
        title={
          <TitleContainer>
            <Video className='mr-8' />
            {t('VideoUpload')}
          </TitleContainer>
        }
      >
        {getVideoUploadDrawer()}
      </Drawer>
    </>
  );
};

export default Navbar;
