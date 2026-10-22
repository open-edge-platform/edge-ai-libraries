// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, SyntheticEvent, useState } from 'react';
import styled from 'styled-components';
import { Checkbox, IconButton, InlineLoading } from '@carbon/react';
import { TrashCan } from '@carbon/icons-react';
import { useTranslation } from 'react-i18next';
import { useAppDispatch } from '../../redux/store';
import { NotificationSeverity, notify } from '../Notification/notify';
import PopupModal from '../PopupModal/PopupModal';
import { SearchRemove, SearchSelector, SearchWatch } from '../../redux/search/searchSlice';
import { useAppSelector } from '../../redux/store';
import { SearchQuery, SearchQueryStatus } from '../../redux/search/search';

const SidebarItemWrapper = styled.div`
  display: flex;
  flex-flow: row nowrap;
  background-color: #fff;

  padding: 0 1rem;
  cursor: pointer;
  transition:
    background-color 0.3s,
    color 0.3s;
  display: flex;
  align-items: center;
  justify-content: space-between;

  border-radius: 0;
  border-right: 4px solid transparent;

  /* Checkbox, spinner and delete button keep their intrinsic size; only the
     query body absorbs the shrinking. */
  > *:not(.query-body) {
    flex: 0 0 auto;
  }

  /* Owns the row's flexible space so the query text and its metadata never
     compete for width. Without this the meta (nowrap, min-width: auto) holds
     its full size while the query text collapses to nothing. */
  .query-body {
    display: flex;
    flex-flow: column nowrap;
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
  }

  .text-container {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .refresh-meta {
    font-size: 0.75rem;
    color: #6f6f6f;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .refresh-meta.error-meta {
    color: #da1e28;
  }

  &.unread {
    border-color: #0f62fe;
    background-color: #edf5ff;
    
    .text-container {
      color: #0f62fe;
      font-weight: 500;
    }
    
    &::before {
      content: "● ";
      color: #0f62fe;
      font-weight: bold;
      margin-right: 4px;
    }
  }

  &.error {
    /* border-color: #da1e28; */
    background-color: #fdf2f2;
    
    .text-container {
      color: #da1e28;
      font-weight: 500;
    }
    
    &::before {
      content: "⚠ ";
      color: #da1e28;
      font-weight: bold;
      margin-right: 4px;
    }
  }

  &.running {
    .text-container {
      color: #0f62fe;
    }
  }

  .running-indicator {
    display: inline-flex;
    align-items: center;
    flex: 0 0 auto;
    margin-left: 0.5rem;
  }

  &.selected,
  &:hover {
    border-radius: 0.25rem;
    background-color: var(--color-active);
  }
`;

export interface SearchSidebarItemProps {
  selected: boolean;
  item: SearchQuery;
  isUnread: boolean;
  onClick?: () => void;
}

export const SearchSidebarItem: FC<SearchSidebarItemProps> = ({ item, selected, isUnread, onClick }) => {
  const { t } = useTranslation();

  const dispatch = useAppDispatch();
  const { refreshConfig } = useAppSelector(SearchSelector);

  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const hasError = item.queryStatus === SearchQueryStatus.ERROR;
  // Image searches have no text query; show a descriptive label instead.
  const displayLabel = item.query || (item.image ? t('searchByImage') : '');
  const isRunning = item.queryStatus === SearchQueryStatus.RUNNING;

  // Watched queries are refreshed by the backend on a fixed cadence, and only
  // when new embeddings were indexed since the previous refresh.
  const autoRefreshEnabled = refreshConfig?.enabled !== false;
  const refreshSeconds = Math.round((refreshConfig?.intervalMs ?? 0) / 1000);

  const watchHint = !autoRefreshEnabled
    ? t('autoRefreshUnavailable')
    : item.watch
      ? refreshSeconds > 0
        ? t('autoRefreshEnabledHint', { seconds: refreshSeconds })
        : t('autoRefreshLabel')
      : t('autoRefreshDisabledHint');

  const lastRefreshedLabel = item.lastRefreshedAt
    ? t('autoRefreshLastUpdated', {
        time: new Date(item.lastRefreshedAt).toLocaleTimeString(),
      })
    : t('autoRefreshNeverUpdated');

  const handleCheckboxChange = (checked: boolean) => {
    if (checked) {
      dispatch(SearchWatch({ queryId: item.queryId, watch: true }));
    } else {
      dispatch(SearchWatch({ queryId: item.queryId, watch: false }));
    }
  };

  const handleDeleteClick = (e: SyntheticEvent) => {
    e.stopPropagation();
    setShowDeleteModal(true);
  };

  const handleDeleteConfirm = async () => {
    setShowDeleteModal(false);
    try {
      dispatch(SearchRemove(item.queryId));
      notify(t('queryDeleteSuccess'), NotificationSeverity.SUCCESS);
    } catch {
      notify(t('queryDeleteFailure'), NotificationSeverity.ERROR);
    }
  };

  const handleDeleteCancel = () => {
    setShowDeleteModal(false);
  };

  return (
    <>
      <SidebarItemWrapper
        className={
          (selected ? 'selected ' : '') +
          (isUnread ? 'unread ' : '') +
          (isRunning ? 'running ' : '') +
          (hasError ? 'error' : '')
        }
        onClick={onClick}
      >
        <Checkbox
          checked={item.watch}
          disabled={!autoRefreshEnabled}
          onChange={(_, { checked }) => {
            handleCheckboxChange(checked);
          }}
          labelText=''
          aria-label={t('autoRefreshLabel')}
          title={watchHint}
          id={`${item.queryId}-sync`}
        />

        <span className='query-body'>
          <span
            className='text-container'
            title={hasError && item.errorMessage ? item.errorMessage : displayLabel}
          >
            {displayLabel}
          </span>

          {hasError && item.errorMessage && (
            <span className='refresh-meta error-meta' title={item.errorMessage}>
              {item.errorMessage}
            </span>
          )}

          {!hasError && item.watch && autoRefreshEnabled && !isRunning && (
            <span className='refresh-meta' title={watchHint}>
              {lastRefreshedLabel}
            </span>
          )}
        </span>

        {isRunning && (
          <span className='running-indicator' data-testid={`search-running-${item.queryId}`}>
            <InlineLoading status='active' description='' aria-label={t('searchRunning')} />
          </span>
        )}

        <IconButton kind='ghost' label={t('queryDeleteLabel')} autoAlign onClick={handleDeleteClick}>
          <TrashCan />
        </IconButton>
      </SidebarItemWrapper>

      {showDeleteModal && (
        <PopupModal
          open={showDeleteModal}
          onOpen={setShowDeleteModal}
          headingMsg={t('queryDelete')}
          primaryButtonText={t('delete')}
          secondaryButtonText={t('cancel')}
          onSubmit={handleDeleteConfirm}
          onClose={handleDeleteCancel}
        >
          <p>
            {t('thisWillDelete')}
            <strong>{`${displayLabel}`}</strong>.
          </p>
        </PopupModal>
      )}
    </>
  );
};
