// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useEffect } from 'react';
import { IconButton } from '@carbon/react';
import styled from 'styled-components';
import { useTranslation } from 'react-i18next';
import { useAppDispatch, useAppSelector } from '../../redux/store.ts';
import { SummaryActions, SummaryLoad, SummarySelector } from '../../redux/summary/summarySlice.ts';
import SummarySideBarItem from './SummarySideBarItem.tsx';
import { VideoChunkActions } from '../../redux/summary/videoChunkSlice.ts';
import { VideoFramesAction } from '../../redux/summary/videoFrameSlice.ts';

const SidebarContainer = styled.aside<{ disabled: boolean }>`
  display: flex;
  flex-direction: column;
  background-color: var(--color-sidebar);
  overflow: hidden;
  border-right: 1px solid var(--color-border);
  pointer-events: ${({ disabled }) => (disabled ? 'none' : 'auto')};
  opacity: ${({ disabled }) => (disabled ? 0.5 : 1)};
  height: 100%;
`;

export const Navigation = styled.div`
  padding: 1rem;
  background-color: var(--color-sidebar);
  position: sticky;
  z-index: 1;
  border-bottom: 1px solid var(--color-border);
  max-height: 3rem;
`;

const ScrollableContainer = styled.div`
  flex-grow: 1;
  overflow-y: auto;
  padding: 5px;
  height: 80vh;
  overflow-x: hidden;
`;

export const StyledIconButton = styled(IconButton)`
  font-size: var(--icon-size);
`;

export const SummarySidebar: FC = () => {
  const { sidebarSummaries } = useAppSelector(SummarySelector);

  const { t } = useTranslation();

  const dispatch = useAppDispatch();

  const selectSummary = (stateId: string) => {
    dispatch(SummaryActions.selectSummary(stateId));
    dispatch(VideoChunkActions.setSelectedSummary(stateId));
    dispatch(VideoFramesAction.selectSummary(stateId));
  };

  useEffect(() => {
    dispatch(SummaryLoad());
  }, []);

  const sidebarList = sidebarSummaries.map((curr) => (
    <SummarySideBarItem
      item={curr}
      key={curr.stateId}
      onClick={() => {
        selectSummary(curr.stateId);
      }}
    />
  ));

  return (
    <>
      <SidebarContainer disabled={false}>
        <Navigation>{t('Summaries')}</Navigation>
        <ScrollableContainer>{sidebarList}</ScrollableContainer>
      </SidebarContainer>
    </>
  );
};

export default SummarySidebar;
