// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { IconButton, Stack } from '@carbon/react';
import {
  useState,
  useRef,
  useEffect,
  type SyntheticEvent,
  type FC,
  type ReactNode,
} from 'react';
import styled from 'styled-components';
import { Edit, TrashCan } from '@carbon/icons-react';
import { useTranslation } from 'react-i18next';

import { NotificationSeverity, notify } from '../Notification/notify.ts';
import PopupModal from '../PopupModal/PopupModal.tsx';
import {
  conversationSelector,
  deleteConversation,
  updateConversationTitle,
} from '../../redux/conversation/conversationSlice.ts';
import { useAppDispatch, useAppSelector } from '../../redux/store.ts';

interface ConversationSideBarItemProps {
  title?: string;
  index: string;
  children?: ReactNode;
  isActive?: boolean;
  onClick?: (e: SyntheticEvent) => void;
}

const ConversationSideBarItemWrapper = styled(Stack)<{
  $isActive: boolean;
  $isHovered: boolean;
}>`
  padding: 10px 2px 10px 10px;
  cursor: pointer;
  transition:
    background-color 0.3s,
    color 0.3s;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 40px;
  border-radius: ${({ $isActive, $isHovered }) =>
    $isActive || $isHovered ? '5px' : '0'};
  background-color: ${({ $isActive, $isHovered }) =>
    $isActive || $isHovered ? 'var(--color-active)' : 'transparent'};
`;

const TextContainer = styled.div`
  flex-grow: 1;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
`;

const IconContainer = styled.div`
  display: flex;
  align-items: center;
  height: 100%;
`;

const EditableInput = styled.input`
  width: 100%;
  padding: 5px;
  font-size: 1rem;
  border: 1px solid var(--color-gray-2);
  border-radius: 4px;
`;

const StyledIconButton = styled(IconButton)`
  border-width: 0;
`;

const StyledPara = styled.p`
  margin: 1rem;
`;

const ConversationSideBarItem: FC<ConversationSideBarItemProps> = ({
  title,
  index,
  isActive = false,
  onClick,
}) => {
  const { t } = useTranslation();
  const [isHovered, setIsHovered] = useState<boolean>(false);
  const [showDeleteModal, setShowDeleteModal] = useState<boolean>(false);
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editedTitle, setEditedTitle] = useState<string>(title || '');
  const { isGenerating } = useAppSelector(conversationSelector);

  const dispatch = useAppDispatch();
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDeleteClick = (e: SyntheticEvent) => {
    e.stopPropagation();
    setShowDeleteModal(true);
  };

  const handleDeleteConfirm = async () => {
    setShowDeleteModal(false);
    try {
      dispatch(deleteConversation(index));
      notify(t('conversationDeletionSuccessful'), NotificationSeverity.SUCCESS);
    } catch {
      notify(t('conversationDeletionFailed'), NotificationSeverity.ERROR);
    }
  };

  const handleDeleteCancel = () => {
    setShowDeleteModal(false);
  };

  const handleEditClick = (e: SyntheticEvent) => {
    e.stopPropagation();
    setIsEditing(true);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setEditedTitle(e.target.value);
  };

  const handleInputBlur = () => {
    setIsEditing(false);
    setEditedTitle(title || t('newChat'));
  };

  const handleInputKeyDown = async (
    e: React.KeyboardEvent<HTMLInputElement>,
  ) => {
    if (e.key === 'Enter') {
      if (editedTitle.trim() === '') {
        notify(t('nonEmptyConversationTitle'), NotificationSeverity.WARNING);
        setEditedTitle(title || t('newChat'));
      } else {
        try {
          dispatch(
            updateConversationTitle({ id: index, updatedTitle: editedTitle }),
          );
        } catch {
          notify(
            t('updateConversationTitleFailed'),
            NotificationSeverity.ERROR,
          );
        }
      }
      setIsEditing(false);
    }
  };

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isEditing]);

  return (
    <>
      <ConversationSideBarItemWrapper
        key={index}
        orientation='vertical'
        $isActive={isActive}
        $isHovered={isHovered}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        data-testid='conversation-sidebar-wrapper'
      >
        <TextContainer onClick={onClick}>
          {isEditing ? (
            <EditableInput
              ref={inputRef}
              value={editedTitle}
              onChange={handleInputChange}
              onBlur={handleInputBlur}
              onKeyDown={handleInputKeyDown}
            />
          ) : (
            title
          )}
        </TextContainer>
        {!isGenerating ? (
          <IconContainer>
            {(isHovered || isActive) && !isEditing && (
              <>
                <StyledIconButton
                  kind='tertiary'
                  size='sm'
                  onClick={handleEditClick}
                  data-testid='edit-conversation-button'
                  label=''
                >
                  <Edit />
                </StyledIconButton>
                <StyledIconButton
                  kind='tertiary'
                  size='sm'
                  onClick={handleDeleteClick}
                  data-testid='delete-conversation-button'
                  label=''
                >
                  <TrashCan />
                </StyledIconButton>
              </>
            )}
          </IconContainer>
        ) : null}
      </ConversationSideBarItemWrapper>

      {showDeleteModal && (
        <PopupModal
          open={showDeleteModal}
          onOpen={setShowDeleteModal}
          headingMsg={t('deleteChat')}
          primaryButtonText={t('delete')}
          secondaryButtonText={t('cancel')}
          onSubmit={handleDeleteConfirm}
          onClose={handleDeleteCancel}
        >
          <StyledPara>
            {t('thisWillDelete')}
            <strong>{`${title || t('newChat')}`}</strong>.
          </StyledPara>
        </PopupModal>
      )}
    </>
  );
};

export default ConversationSideBarItem;
