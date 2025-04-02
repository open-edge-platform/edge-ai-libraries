// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Document } from '@carbon/icons-react';
import { type FC, type ChangeEvent, useState, useRef } from 'react';
import styled from 'styled-components';
import { useTranslation } from 'react-i18next';
import { unwrapResult } from '@reduxjs/toolkit';
import { AxiosError } from 'axios';

import { useAppDispatch, useAppSelector } from '../../redux/store.ts';
import {
  conversationSelector,
  fetchInitialFiles,
  uploadFile,
} from '../../redux/conversation/conversationSlice.ts';
import { notify } from '../../components/Notification/notify.ts';
import { NotificationSeverity } from '../../components/Notification/notify.ts';
import { acceptedFormat, MAX_FILE_SIZE } from '../../utils/constant.ts';
import { StyledModelWrapper } from '../Conversation/Conversation.tsx';

interface DataSourceProps {
  buttonDisabled?: boolean;
  close: () => void;
}

const DataSourceWrapper = styled.div`
  margin-bottom: 1rem;
`;

const StyledButton = styled.button`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.5rem 2rem;
  font-size: 0.875rem;
  font-weight: 600;
  line-height: 1.29;
  border: none;
  cursor: pointer;
  transition:
    background-color 0.15s ease-in-out,
    color 0.15s ease-in-out;
  background-color: var(--color-info);
  color: var(--color-white);
  margin-top: 1rem;
  &:hover {
    background-color: var(--color-button-hover);
  }
  &:active {
    background-color: var(--color-button-active);
  }
  &:disabled {
    background-color: var(--color-button-disabled);
    color: var(--color-white);
    cursor: not-allowed;
  }
  &:focus {
    outline: 2px solid var(--color-info);
    outline-offset: 2px;
  }
`;

const FileContainer = styled.div`
  margin-top: 2rem;
  display: flex;
  align-items: center;
  max-width: 400px;
  background-color: var(--color-sidebar);
  line-height: 1.3;
`;

const FileIcon = styled.div`
  font-size: 0.875rem;
  color: var(--color-black);
  padding: 0.5rem;
`;

const FileName = styled.div`
  font-size: 0.875rem;
  color: var(--color-black);
  padding: 0.5rem;
  word-break: break-word;
`;

const StyledList = styled.ul`
  font-size: 0.8rem;
  list-style-type: disc;
  padding-left: 1.5rem;
  margin: 1rem auto;
  margin-bottom: 1rem;

  & li {
    padding-bottom: 0.6rem;

    &:last-child {
      padding-bottom: 0;
    }
  }
`;

const DataSource: FC<DataSourceProps> = ({ close }) => {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [isValidFile, setIsValidFile] = useState<boolean>(true);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const dispatch = useAppDispatch();
  const { files } = useAppSelector(conversationSelector);

  const handleFileUpload = async (): Promise<void> => {
    if (file) {
      try {
        close();
        notify(t('fileUploadStarted'), NotificationSeverity.INFO);
        const response = await dispatch(uploadFile({ file }));
        unwrapResult(response);
        notify(t('fileUploadSuccessful'), NotificationSeverity.SUCCESS);
        dispatch(fetchInitialFiles());
      } catch (error) {
        const axiosError = error as AxiosError;
        notify(`${axiosError.message}`, NotificationSeverity.ERROR);
      } finally {
        setFile(null);
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
      }
    }
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>): void => {
    event.preventDefault();
    const selectedFile = event.target.files ? event.target.files[0] : null;

    if (selectedFile) {
      const isDuplicate = files.includes(selectedFile.name);
      if (isDuplicate) {
        notify(t('duplicateFileNotification'), NotificationSeverity.WARNING);
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
        return;
      }
      const fileSizeMB = selectedFile.size / 1024 / 1024;
      if (!acceptedFormat.includes(selectedFile.type)) {
        notify(t('formatNotification'), NotificationSeverity.ERROR);
        setFile(null);
        setIsValidFile(false);
      } else if (fileSizeMB > MAX_FILE_SIZE) {
        notify(`${t('fileSizeExceeded')}`, NotificationSeverity.WARNING);
        setFile(null);
        setIsValidFile(false);
      } else {
        setFile(selectedFile);
        setIsValidFile(true);
      }
    } else {
      setFile(null);
      setIsValidFile(true);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return (
    <DataSourceWrapper data-testid='data-source-wrapper'>
      <StyledList>
        <li>{t('acceptedFileText')}</li>
        <li>{t('acceptedSizeText')}</li>
      </StyledList>
      <StyledButton
        onClick={() => fileInputRef.current?.click()}
        data-testid='add-file-button'
      >
        {t('addFile')}
      </StyledButton>

      {file && (
        <FileContainer data-testid='file-container'>
          <FileIcon>
            <Document size='1.5rem' />
          </FileIcon>
          <FileName>{file.name}</FileName>
        </FileContainer>
      )}
      <input
        ref={fileInputRef}
        type='file'
        accept={acceptedFormat.join(',')}
        style={{ display: 'none' }}
        onChange={handleFileChange}
        data-testid='file-input-field'
      />

      <StyledModelWrapper>
        {file && (
          <StyledButton
            disabled={!file || !isValidFile}
            onClick={handleFileUpload}
            data-testid='file-upload-button'
          >
            {t('upload')}
          </StyledButton>
        )}
      </StyledModelWrapper>
    </DataSourceWrapper>
  );
};

export default DataSource;
