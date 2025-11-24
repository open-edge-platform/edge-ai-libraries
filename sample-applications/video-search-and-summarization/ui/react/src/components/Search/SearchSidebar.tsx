// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { IconButton } from '@carbon/react';
import { Renew } from '@carbon/react/icons';
import { FC } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { SearchSidebarItem } from './SearchSidebarItem';
import { SearchActions, SearchLoad, SearchSelector } from '../../redux/search/searchSlice';
import { SearchQueryStatus } from '../../redux/search/search';

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
  display: flex;
  flex-flow: row nowrap;
  align-items: center;
  justify-content: flex-start;
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

export const SearchSidebar: FC = () => {
  const { queries, selectedQueryId, unreads, queriesInProgress } = useAppSelector(SearchSelector);

  const { t } = useTranslation();

  const dispatch = useAppDispatch();

  const selectQuery = (queryId: string) => {
    dispatch(SearchActions.selectQuery(queryId));
  };

  const filteredQueries = queries.filter((query) =>query.queryStatus !== SearchQueryStatus.ERROR && query.results && query.results.length > 0);
  const sidebarList = filteredQueries.map((curr) => (
    <SearchSidebarItem
      item={curr}
      selected={selectedQueryId === curr.queryId}
      key={curr.queryId}
      isUnread={unreads.includes(curr.queryId)}
      onClick={() => {
        selectQuery(curr.queryId);
      }}
    />
  ));

  return (
    <>
      <SidebarContainer disabled={false} data-tour="previous-searches">
        <Navigation>
          {t('Queries')}
          <span className='spacer'></span>
          <IconButton kind='ghost' label={t('Refetch')} autoAlign onClick={() => dispatch(SearchLoad())} size='sm'>
            <Renew />
          </IconButton>
        </Navigation>
        {queriesInProgress.length > 0 && (
          <Navigation>
            <span className='spacer'></span>
            <span>{t('AddingSearches', { count: queriesInProgress.length })}</span>
          </Navigation>
        )}
        <ScrollableContainer>{sidebarList}</ScrollableContainer>
      </SidebarContainer>
    </>
  );
};

export default SearchSidebar;
