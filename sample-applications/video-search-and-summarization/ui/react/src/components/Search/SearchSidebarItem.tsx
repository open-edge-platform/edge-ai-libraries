// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, SyntheticEvent, useState } from 'react';
import styled from 'styled-components';
import { Checkbox, IconButton } from '@carbon/react';
import { TrashCan } from '@carbon/icons-react';
import { useTranslation } from 'react-i18next';
import { useAppDispatch } from '../../redux/store';
import { NotificationSeverity, notify } from '../Notification/notify';
import PopupModal from '../PopupModal/PopupModal';
import { SearchRemove, SearchWatch } from '../../redux/search/searchSlice';
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

  .text-container {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
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

  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const hasError = item.queryStatus === SearchQueryStatus.ERROR;

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
      <SidebarItemWrapper className={(selected ? 'selected ' : '') + (isUnread ? 'unread ' : '') + (hasError ? 'error' : '')} onClick={onClick}>
        <Checkbox
          checked={item.watch}
          onChange={(_, { checked }) => {
            handleCheckboxChange(checked);
          }}
          labelText=''
          id={`${item.queryId}-sync`}
        />

        <span className='text-container'>
          {item.query}
        </span>

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
            <strong>{`${item.query}`}</strong>.
          </p>
        </PopupModal>
      )}
    </>
  );
};
