// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC } from 'react';
import SummaryMainContainer from '../Summaries/SummaryContainer';
import SearchMainContainer from '../Search/SearchContainer';
import { IconButton } from '@carbon/react';
import { DataAnalytics, Sigma } from '@carbon/react/icons';
import styled from 'styled-components';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { UIActions, uiSelector } from '../../redux/ui/ui.slice';
import { MuxFeatures } from '../../redux/ui/ui.model';

const SuperSidebar = styled.div`
  display: flex;
  flex-flow: column nowrap;
  align-items: flex-start;
  justify-content: flex-start;
  background-color: var(--color-sidebar);
  border-right: 1px solid var(--color-border);
`;

export const SplashSummarySearch: FC = () => {
  const dispatch = useAppDispatch();
  const { selectedMux } = useAppSelector(uiSelector);

  return (
    <>
      <SuperSidebar>
        <IconButton
          align='right'
          label='Summary'
          onClick={() => dispatch(UIActions.setMux(MuxFeatures.SUMMARY))}
          kind={selectedMux == MuxFeatures.SUMMARY ? 'primary' : 'ghost'}
        >
          <Sigma />
        </IconButton>
        <IconButton
          align='right'
          label='Search'
          onClick={() => dispatch(UIActions.setMux(MuxFeatures.SEARCH))}
          kind={selectedMux == MuxFeatures.SEARCH ? 'primary' : 'ghost'}
        >
          <DataAnalytics />
        </IconButton>
      </SuperSidebar>

      {MuxFeatures.SUMMARY === selectedMux && <SummaryMainContainer />}
      {MuxFeatures.SEARCH === selectedMux && <SearchMainContainer />}
    </>
  );
};
