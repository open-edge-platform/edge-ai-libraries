// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { SyntheticEvent, useState, type FC } from 'react';
import styled from 'styled-components';

import { UISummaryState } from '../../redux/summary/summary.ts';
import { IconButton } from '@carbon/react';
import { TrashCan } from '@carbon/icons-react';
import { useTranslation } from 'react-i18next';
import PopupModal from '../PopupModal/PopupModal.tsx';
import { NotificationSeverity, notify } from '../Notification/notify.ts';
import { useAppDispatch } from '../../redux/store.ts';
import { SummaryRemove } from '../../redux/summary/summarySlice.ts';

const SidebarWrapper = styled.div`
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

  &.selected,
  &:hover {
    border-radius: 0.25rem;
    background-color: var(--color-active);
  }
  .text-container {
    overflow: hidden;
    text-overflow: ellipsis;
  }
`;

interface SidebarItemWithSelect extends UISummaryState {
  selected: boolean;
}

export interface SummarySideBarItemProps {
  item: SidebarItemWithSelect;
  onClick?: () => void;
}

export const SummarySideBarItem: FC<SummarySideBarItemProps> = ({ item, onClick }) => {
  const { t } = useTranslation();

  const dispatch = useAppDispatch();

  const [showDeleteModal, setShowDeleteModal] = useState(false);

  const handleDeleteClick = (e: SyntheticEvent) => {
    e.stopPropagation();
    setShowDeleteModal(true);
  };

  const handleDeleteConfirm = async () => {
    setShowDeleteModal(false);
    try {
      dispatch(SummaryRemove(item.stateId));
      notify(t('summaryDeleteSuccess'), NotificationSeverity.SUCCESS);
    } catch {
      notify(t('summaryDeleteFailed'), NotificationSeverity.ERROR);
    }
  };

  const handleDeleteCancel = () => {
    setShowDeleteModal(false);
  };

  return (
    <>
      <SidebarWrapper
        onClick={() => {
          if (onClick) {
            onClick();
          }
        }}
        className={item.selected ? 'selected' : ''}
      >
        <span className='text-container' title={item.title}>
          {item.title}
        </span>
        <IconButton align='left' kind='ghost' onClick={handleDeleteClick} label={t('deleteSummaryLabel')}>
          <TrashCan />
        </IconButton>
      </SidebarWrapper>

      {showDeleteModal && (
        <PopupModal
          open={showDeleteModal}
          onOpen={setShowDeleteModal}
          headingMsg={t('deleteSummary')}
          primaryButtonText={t('delete')}
          secondaryButtonText={t('cancel')}
          onSubmit={handleDeleteConfirm}
          onClose={handleDeleteCancel}
        >
          <p>
            {t('thisWillDelete')}
            <strong>{item.title}</strong>.
          </p>
        </PopupModal>
      )}
    </>
  );
};

export default SummarySideBarItem;
