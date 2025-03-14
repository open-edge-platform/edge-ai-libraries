// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState, type FC } from 'react';
import { useTranslation } from 'react-i18next';
import { unwrapResult } from '@reduxjs/toolkit';

import PopupModal from '../PopupModal/PopupModal.tsx';
import { extractBetweenDotsWithExtension } from '../../utils/util.ts';
import { NotificationSeverity, notify } from '../Notification/notify.ts';
import { useAppDispatch, useAppSelector } from '../../redux/store.ts';
import { File } from '../../redux/conversation/conversation.ts';
import {
  removeAllFiles,
  removeAllLinks,
  removeFile,
  removeLink,
  conversationSelector,
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
  ScrollableContainer,
  Strong,
  FileLinkManagerWrapper,
} from './FileLinkManagerStyles.ts';

interface FileLinkManagerProps {
  isFile?: boolean;
  closeDrawer: () => void;
  showField: boolean;
}

const FileLinkManager: FC<FileLinkManagerProps> = ({
  isFile = true,
  closeDrawer,
  showField,
}) => {
  const { t } = useTranslation();
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [selectedLinks, setSelectedLinks] = useState<string[]>([]);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [deleteAll, setDeleteAll] = useState<boolean>(false);

  const { files = [], links = [] } = useAppSelector(conversationSelector) || {};
  const items = isFile ? files : links;

  const selectedItems = isFile ? selectedFiles : selectedLinks;

  const dispatch = useAppDispatch();

  useEffect(() => {
    const currentSelectedItems = isFile ? selectedFiles : selectedLinks;
    setDeleteAll(
      items.length > 0 && currentSelectedItems.length === items.length,
    );
  }, [isFile, selectedFiles, selectedLinks, items]);

  const handleConfirmDelete = async () => {
    setIsModalOpen(false);
    closeDrawer();
    try {
      if (deleteAll) {
        const response = isFile
          ? await dispatch(
              removeAllFiles({ bucketName: (items[0] as File).bucket_name }),
            )
          : await dispatch(removeAllLinks({ deleteAll: true }));
        const result = unwrapResult(response);
        if (result.status >= 200 && result.status <= 204) {
          notify(
            isFile
              ? t('filesSuccessfullyDeleted')
              : t('linksSuccessfullyDeleted'),
            NotificationSeverity.SUCCESS,
          );
        } else {
          notify(
            isFile ? t('failedToDeleteFiles') : t('failedToDeleteLinks'),
            NotificationSeverity.ERROR,
          );
        }
      } else {
        const currentSelectedItems = isFile ? selectedFiles : selectedLinks;
        for (const item of currentSelectedItems) {
          const response = isFile
            ? await dispatch(
                removeFile({
                  fileName: (item as File).file_name,
                  bucketName: (item as File).bucket_name,
                }),
              )
            : await dispatch(
                removeLink({
                  linkName: item as string,
                }),
              );
          try {
            const result = unwrapResult(response);
            const { status, message } = result;
            const itemName =
              'fileName' in result ? result.fileName : result.linkName;
            if (status >= 200 && status <= 204) {
              notify(
                `${isFile ? t('file') : t('link')} ${
                  isFile ? extractBetweenDotsWithExtension(itemName) : itemName
                } ${t('deletedSuccessfully')}`,
                NotificationSeverity.SUCCESS,
              );
            } else {
              notify(
                `${isFile ? t('failedToDeleteFile') : t('failedToDeleteLink')} ${
                  isFile ? extractBetweenDotsWithExtension(itemName) : itemName
                }: ${message}`,
                NotificationSeverity.ERROR,
              );
            }
          } catch (error) {
            if (error instanceof Error) {
              notify(
                `${t('unexpectedError')}: ${error.message}`,
                NotificationSeverity.ERROR,
              );
            } else if (
              typeof error === 'object' &&
              error !== null &&
              'status' in error
            ) {
              const { status, message } = error as {
                status: number;
                message: string;
              };
              if (status === 404) {
                notify(
                  isFile ? t('fileNotFound') : t('linkNotFound'),
                  NotificationSeverity.ERROR,
                );
              } else {
                notify(
                  `${t('errorWithUpperCase')}: ${message}`,
                  NotificationSeverity.ERROR,
                );
              }
            } else {
              notify(t('unknownError'), NotificationSeverity.ERROR);
            }
          }
        }
      }
    } finally {
      if (isFile) {
        setSelectedFiles([]);
      } else {
        setSelectedLinks([]);
      }
      setDeleteAll(false);
    }
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
  };

  const handleSelectItem = (item: File | string) => {
    if (isFile) {
      setSelectedFiles((prevSelectedFiles) =>
        prevSelectedFiles.some((f) => f.file_name === (item as File).file_name)
          ? prevSelectedFiles.filter(
              (f) => f.file_name !== (item as File).file_name,
            )
          : [...prevSelectedFiles, item as File],
      );
    } else {
      setSelectedLinks((prevSelectedLinks) =>
        prevSelectedLinks.some((f) => f === (item as string))
          ? prevSelectedLinks.filter((f) => f !== (item as string))
          : [...prevSelectedLinks, item as string],
      );
    }
  };

  const handleDeleteSelected = () => {
    setIsModalOpen(true);
  };

  const handleDeleteAll = () => {
    setDeleteAll(true);
    setIsModalOpen(true);
  };

  return (
    <FileLinkManagerWrapper data-testid='file-link-manager-wrapper'>
      <Container>
        <Strong data-testid='files-heading-wrapper'>
          {isFile ? t('files') : t('links')}
        </Strong>
        <StyledButtonSet>
          <Button
            onClick={handleDeleteSelected}
            disabled={
              isFile ? selectedFiles.length === 0 : selectedLinks.length === 0
            }
            data-testid='handle-delete-selected-button'
          >
            {t('deleteSelected')}
          </Button>
          <Button
            onClick={handleDeleteAll}
            disabled={items.length === 0}
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
                <TableHeader>
                  {isFile ? t('fileName') : t('linkName')}
                </TableHeader>
              </TableRow>
            </TableHead>

            <TableBody>
              {items.map((item, index) => (
                <TableRow key={index}>
                  <TableCell>
                    <Checkbox
                      checked={selectedItems.some((f) =>
                        isFile
                          ? (f as File).file_name === (item as File).file_name
                          : (f as string) === (item as string),
                      )}
                      onChange={() => handleSelectItem(item)}
                    />
                  </TableCell>
                  <TableCell>
                    {isFile
                      ? extractBetweenDotsWithExtension(
                          (item as File).file_name,
                        )
                      : (item as string)}
                  </TableCell>
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
        primaryButtonText={t('delete')}
        secondaryButtonText={t('cancel')}
        headingMsg={isFile ? t('deleteFiles') : t('deleteLinks')}
      >
        <p>
          {isFile ? t('deleteFileDescription') : t('deleteLinkDescription')}
        </p>
        <StyledList>
          {deleteAll
            ? items.map((item, index) => (
                <li key={index}>
                  {isFile
                    ? extractBetweenDotsWithExtension((item as File).file_name)
                    : (item as string)}
                </li>
              ))
            : selectedItems.map((item, index) => (
                <li key={index}>
                  {isFile
                    ? extractBetweenDotsWithExtension((item as File).file_name)
                    : (item as string)}
                </li>
              ))}
        </StyledList>
      </PopupModal>
    </FileLinkManagerWrapper>
  );
};

export default FileLinkManager;
