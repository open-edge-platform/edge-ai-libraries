// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect, type FC } from 'react';
import styled, { css } from 'styled-components';
import { useTranslation } from 'react-i18next';

import Notice from '../Notice/Notice.tsx';
import Navbar from '../Navbar/Navbar.tsx';
import SummarySidebar from '../Summaries/SummarySideBar';
import Summary from '../Summaries/Summary.tsx';
import SearchMainContainer from '../Search/SearchContainer.tsx';
import OnboardingTour from '../Tour/OnboardingTour.tsx';
import { SplashSummarySearch } from './SplashMux.tsx';
import { useAppSelector } from '../../redux/store.ts';
import { uiSelector } from '../../redux/ui/ui.slice.ts';
import { MuxFeatures } from '../../redux/ui/ui.model.ts';
import { SummarySelector } from '../../redux/summary/summarySlice.ts';
import { SearchSelector } from '../../redux/search/searchSlice.ts';
import { FEATURE_SEARCH, FEATURE_SUMMARY } from '../../config.ts';
import { FEATURE_STATE } from '../../utils/constant.ts';

const StyledGrid = styled.div<{ $super?: boolean }>`
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-columns: 15rem auto;
  grid-template-rows: 1fr;
  ${(props) =>
    props.$super &&
    css`
      grid-template-columns: 3rem 15rem auto;
    `}
  flex: 1 1 auto;
  overflow: hidden;
  @media (min-width: 1700px) {
    grid-template-columns: 20rem auto;
    ${(props) =>
      props.$super &&
      css`
        grid-template-columns: 3rem 20rem auto;
      `}
  }
  @media (min-width: 2000px) {
    grid-template-columns: 25rem auto;
    ${(props) =>
      props.$super &&
      css`
        grid-template-columns: 3rem 25rem auto;
      `}
  }
  @media (min-width: 2300px) {
    grid-template-columns: 30rem auto;
    ${(props) =>
      props.$super &&
      css`
        grid-template-columns: 3rem 30rem auto;
      `}
  }
`;

const StyledMain = styled.main`
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  display: flex;
  flex-flow: column nowrap;
  align-items: flex-start;
  justify-content: flex-start;
`;

const HiddenButton = styled.button`
  display: none;
`;

const MainPage: FC = () => {
  const { t } = useTranslation();
  const message = <div>{t('noticeMessage')}</div>;
  const [isNoticeVisible, setIsNoticeVisible] = useState<boolean>(false);
  const [showTour, setShowTour] = useState<boolean>(false);
  const [dataLoaded, setDataLoaded] = useState<boolean>(false);

  const { selectedMux } = useAppSelector(uiSelector);
  const { sidebarSummaries } = useAppSelector(SummarySelector);
  const { queries } = useAppSelector(SearchSelector);

  useEffect(() => {
    // Mark data as loaded after initial render to prevent premature tour display
    const timer = setTimeout(() => {
      setDataLoaded(true);
    }, 100);
    
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    // Only check for tour after data has been loaded
    if (!dataLoaded) return;
    
    // Check if user has completed the tour
    const tourCompleted = localStorage.getItem('onboarding-tour-completed');
    
    // Show tour only if not completed AND no existing data
    if (!tourCompleted) {
      const hasSummaries = sidebarSummaries.length > 0;
      const hasSearches = queries.length > 0;
      
      // Only show tour if there's truly no data
      if (!hasSummaries && !hasSearches) {
        // Delay showing tour to ensure DOM elements are rendered
        setTimeout(() => setShowTour(true), 500);
      }
    }
  }, [dataLoaded, sidebarSummaries, queries]);

  const handleTourComplete = () => {
    setShowTour(false);
    localStorage.setItem('onboarding-tour-completed', 'true');
  };

  const getTourSteps = () => {
    const hasSearchFeature = FEATURE_SEARCH === FEATURE_STATE.ON;
    const hasBothFeatures = FEATURE_SEARCH === FEATURE_STATE.ON && FEATURE_SUMMARY === FEATURE_STATE.ON;
    
    // Common Step 3: Search Videos (reused in both modes)
    const searchVideosStep = {
      target: '[data-tour="search-video-button"]',
      title: 'Step 3: Search Videos',
      content: 'Use this button to search videos by entering a query. You can describe what you are looking for and filter results by tags to find specific video segments quickly.',
      placement: 'bottom' as const,
    };
    
    if (selectedMux === MuxFeatures.SUMMARY) {
      const steps = [
        {
          target: '[data-tour="create-summary-button"]',
          title: 'Step 1: Create New Summary',
          content: 'Click this button to upload a video and create a new summary. You can customize parameters like summary title, tags, duration for a chunk, sample frames per chunk, and advanced settings. Review your parameters before creating the summary.',
          placement: 'bottom' as const,
        },
        {
          target: '[data-tour="previous-summaries"]',
          title: 'Step 2: Previous Summaries',
          content: 'All your video summaries will appear here. Click on any summary to view its details, chunks, and generated summary.',
          placement: 'right' as const,
        },
      ];
      
      // Add Step 3 for Search Videos button when both features are enabled
      if (hasBothFeatures) {
        steps.push(searchVideosStep);
      }
      
      return steps;
    } else {
      const steps = [
        {
          target: '[data-tour="create-summary-button"]',
          title: 'Step 1: Create New Video Embedding',
          content: 'Click this button to upload a video and create embeddings for search. You can customize tags or choose from available tag options. Review your parameters before creating the embedding.',
          placement: 'bottom' as const,
        },
        {
          target: '[data-tour="previous-searches"]',
          title: 'Step 2: Previous Search Queries',
          content: 'All your search queries will appear here. Click on any query to view the search results and matching video segments.',
          placement: 'right' as const,
        },
      ];
      
      // Add Step 3 for Search Videos button when search feature is enabled
      if (hasSearchFeature) {
        steps.push(searchVideosStep);
      }
      
      return steps;
    }
  };

  return (
    <StyledMain>
      <Navbar />
      <HiddenButton data-testid='toggle-notice' onClick={() => setIsNoticeVisible(true)}>
        t('showNoticeHiddenButton')
      </HiddenButton>

      <Notice message={message} isNoticeVisible={isNoticeVisible} setIsNoticeVisible={setIsNoticeVisible} />
      
      <OnboardingTour 
        steps={getTourSteps()} 
        onComplete={handleTourComplete} 
        isActive={showTour} 
      />
      
      <StyledGrid $super={FEATURE_SEARCH === FEATURE_STATE.ON && FEATURE_SUMMARY === FEATURE_STATE.ON}>
        {/* When both features enabled, show the toggle sidebar */}
        {FEATURE_SEARCH === FEATURE_STATE.ON && FEATURE_SUMMARY === FEATURE_STATE.ON && (
          <SplashSummarySearch />
        )}
        
        {/* When only summary or only search is enabled */}
        {!(FEATURE_SEARCH === FEATURE_STATE.ON && FEATURE_SUMMARY === FEATURE_STATE.ON) && (
          <>
            {selectedMux === MuxFeatures.SUMMARY && (
              <>
                <SummarySidebar />
                <Summary />
              </>
            )}
            {selectedMux === MuxFeatures.SEARCH && <SearchMainContainer />}
          </>
        )}
      </StyledGrid>
    </StyledMain>
  );
};

export default MainPage;
