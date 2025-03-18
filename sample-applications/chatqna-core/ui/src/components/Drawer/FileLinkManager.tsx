// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState, type FC } from 'react';
import { useTranslation } from 'react-i18next';
import { unwrapResult } from '@reduxjs/toolkit';
import { AxiosError } from 'axios';

import PopupModal from '../PopupModal/PopupModal.tsx';
import { NotificationSeverity, notify } from '../Notification/notify.ts';
import { useAppDispatch, useAppSelector } from '../../redux/store.ts';
import {
  conversationSelector,
  removeAllFiles,
  removeFile,
} from '../../redux/conversation/conversationSlice.ts';
import {
  Container,
  StyledButtonSet,
  Button,
  Table,
  TableHead,
  TableRow,
  TableHeader,
  TableBody,
  TableCell,
  Checkbox,
  StyledList,
  Strong,
  ScrollableContainer,
} from './FileLinkManagerStyles.ts';

interface FileLinkManagerProps {
  showField: boolean;
  closeDrawer: () => void;
}

const FileLinkManager: FC<FileLinkManagerProps> = ({
  closeDrawer,
  showField,
}) => {
  const { t } = useTranslation();
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [deleteAll, setDeleteAll] = useState<boolean>(false);

  const dispatch = useAppDispatch();
  const { files = [] } = useAppSelector(conversationSelector) || {};

  useEffect(() => {
    setDeleteAll(files.length > 0 && selectedFiles.length === files.length);
  }, [selectedFiles, files]);

  const handleConfirmDelete = async () => {
    setIsModalOpen(false);
    closeDrawer();
    try {
      if (deleteAll) {
        try {
          const response = await dispatch(removeAllFiles());
          unwrapResult(response);
          notify(t('filesSuccessfullyDeleted'), NotificationSeverity.SUCCESS);
        } catch (error) {
          const axiosError = error as AxiosError;
          notify(`${axiosError.message}`, NotificationSeverity.ERROR);
        }
      } else {
        for (const file of selectedFiles) {
          try {
            const response = await dispatch(
              removeFile({
                fileName: file,
              }),
            );
            const result = unwrapResult(response);
            notify(
              `${t('file')} ${result || file} ${t('deletedSuccessfully')}`,
              NotificationSeverity.SUCCESS,
            );
          } catch (error) {
            const axiosError = error as AxiosError;
            notify(`${axiosError.message}`, NotificationSeverity.ERROR);
          }
        }
      }
    } finally {
      setSelectedFiles([]);
      setDeleteAll(false);
    }
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
  };

  const handleSelectItem = (file: string) => {
    setSelectedFiles((prevSelectedFiles) =>
      prevSelectedFiles.some((f) => f === file)
        ? prevSelectedFiles.filter((f) => f !== file)
        : [...prevSelectedFiles, file],
    );
  };

  const handleDeleteSelected = () => {
    closeDrawer();
    setIsModalOpen(true);
  };

  const handleDeleteAll = () => {
    closeDrawer();
    setDeleteAll(true);
    setIsModalOpen(true);
  };

  return (
    <>
      <Container data-testid='file-link-manager-wrapper'>
        <Strong data-testid='files-heading-wrapper'>{t('files')}</Strong>
        <StyledButtonSet>
          <Button
            onClick={handleDeleteSelected}
            disabled={selectedFiles.length === 0}
            data-testid='handle-delete-selected-button'
          >
            {t('deleteSelected')}
          </Button>
          <Button
            onClick={handleDeleteAll}
            disabled={files.length === 0}
            data-testid='handle-delete-all-button'
          >
            {t('deleteAll')}
          </Button>
        </StyledButtonSet>

        <ScrollableContainer $showField={showField}>
          <Table>
            <TableHead>
              <TableRow>
                <TableHeader></TableHeader>
                <TableHeader>{t('fileName')}</TableHeader>
              </TableRow>
            </TableHead>

            <TableBody>
              {files.map((file, index) => (
                <TableRow key={index}>
                  <TableCell>
                    <Checkbox
                      checked={selectedFiles.some((f) => f === file)}
                      onChange={() => handleSelectItem(file)}
                    />
                  </TableCell>
                  <TableCell>{file}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollableContainer>
      </Container>

      <PopupModal
        open={isModalOpen}
        onOpen={setIsModalOpen}
        onClose={handleCloseModal}
        onSubmit={handleConfirmDelete}
        headingMsg={t('deleteFiles')}
        primaryButtonText={t('confirm')}
        secondaryButtonText={t('cancel')}
      >
        <p>{t('deleteFileDescription')}</p>
        <StyledList>
          {deleteAll
            ? files.map((file, index) => <li key={index}>{file}</li>)
            : selectedFiles.map((file, index) => <li key={index}>{file}</li>)}
        </StyledList>
      </PopupModal>
    </>
  );
};

export default FileLinkManager;
