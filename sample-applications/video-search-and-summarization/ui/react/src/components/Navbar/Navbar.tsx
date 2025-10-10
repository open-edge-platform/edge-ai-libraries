// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState, type FC } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import { Button } from '@carbon/react';
import PromptInputModal from '../Modals/PromptInputModal.tsx';
import { FEATURE_SEARCH, FEATURE_SUMMARY } from '../../config.ts';
import SummarizeModal from '../VideoActions/SummarizeModal';
import VideoEmbeddingModal from '../VideoActions/VideoEmbeddingModal';
import { useAppDispatch } from '../../redux/store.ts';
import { videosLoad } from '../../redux/video/videoSlice.ts';
import { SearchModal } from '../PopupModal/SearchModal.tsx';
import { FEATURE_STATE } from '../../utils/constant.ts';
import { LoadTags } from '../../redux/search/searchSlice.ts';
import { UIActions } from '../../redux/ui/ui.slice.ts';
import { MuxFeatures } from '../../redux/ui/ui.model.ts';

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
  const [showSummarizeModal, setShowSummarizeModal] = useState(false);
  const [showEmbeddingModal, setShowEmbeddingModal] = useState(false);
  const { t } = useTranslation();

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


  const [showSearchModal, setShowSearchModal] = useState<boolean>(false);

  const closeSearchModal = () => {
    setShowSearchModal(false);
  };

  return (
    <>
      {FEATURE_SUMMARY == FEATURE_STATE.ON && <PromptInputModal />}

      {FEATURE_SEARCH == FEATURE_STATE.ON && <SearchModal showModal={showSearchModal} closeModal={closeSearchModal} />}

      <SummarizeModal open={showSummarizeModal} onClose={() => setShowSummarizeModal(false)} />
      
      {FEATURE_SEARCH == FEATURE_STATE.ON && (
        <VideoEmbeddingModal 
          open={showEmbeddingModal} 
          onClose={() => setShowEmbeddingModal(false)} 
        />
      )}

      <StyledDiv>
        <Logo>{getBrandName()}</Logo>
        <span className='spacer'></span>

        {/* Show Search Video button when search is enabled */}
        {FEATURE_SEARCH == FEATURE_STATE.ON && (
          <Button
            kind='primary'
            disabled={false}
            data-tour="search-video-button"
            onClick={() => {
              dispatch(LoadTags());
              // Switch to search view when both features are enabled
              if (FEATURE_SEARCH == FEATURE_STATE.ON && FEATURE_SUMMARY == FEATURE_STATE.ON) {
                dispatch(UIActions.setMux(MuxFeatures.SEARCH));
              }
              setShowSearchModal(true);
            }}
          >
            {t('SearchVideo')}
          </Button>
        )}

        {/* Show main action button based on features */}
        <Button 
          kind='primary' 
          data-tour="create-summary-button"
          onClick={() => {
            const hasSearch = FEATURE_SEARCH == FEATURE_STATE.ON;
            const hasSummary = FEATURE_SUMMARY == FEATURE_STATE.ON;
            
            if (hasSearch && !hasSummary) {
              // Only search feature enabled, open embedding modal
              dispatch(LoadTags());
              setShowEmbeddingModal(true);
            } else {
              // Summary feature enabled (with or without search), open summarize modal
              dispatch(LoadTags());
              // Switch to summary view when both features are enabled
              if (hasSearch && hasSummary) {
                dispatch(UIActions.setMux(MuxFeatures.SUMMARY));
              }
              setShowSummarizeModal(true);
            }
          }} 
          disabled={false}
        >
          {getVideoUploadAction()}
        </Button>
      </StyledDiv>
    </>
  );
};

export default Navbar;