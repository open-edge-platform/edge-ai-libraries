// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { TextInput } from '@carbon/react';
import { Document } from '@carbon/icons-react';
import {
  type FC,
  type ChangeEvent,
  type SyntheticEvent,
  useState,
  useRef,
  useEffect,
} from 'react';
import styled from 'styled-components';
import { useTranslation } from 'react-i18next';
import { unwrapResult } from '@reduxjs/toolkit';

import { useAppDispatch, useAppSelector } from '../../redux/store.ts';
import {
  conversationSelector,
  fetchInitialFiles,
  submitDataSourceURL,
  uploadFile,
} from '../../redux/conversation/conversationSlice.ts';
import { notify } from '../../components/Notification/notify.ts';
import { NotificationSeverity } from '../../components/Notification/notify.ts';
import { acceptedFormat, MAX_FILE_SIZE } from '../../utils/constant.ts';
import {
  extractBetweenDotsWithExtension,
  isValidUrl,
} from '../../utils/util.ts';
import { StyledModelWrapper } from '../Conversation/Conversation.tsx';

interface DataSourceProps {
  isFile?: boolean;
  close: () => void;
}

const DataSourceWrapper = styled.div`
  margin-bottom: 1rem;
`;

const FileDataSourceWrapper = styled.div``;

const LinkDataSourceWrapper = styled.div``;

const StyledTextInput = styled(TextInput)`
  margin-top: 1rem;
  & input {
    border-radius: 3px;

  & label {
    font-size: 10px;
  }
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
  line-height: 1.3;
`;

const Strong = styled.p`
  font-weight: 500;
  margin-bottom: 0.5rem;
  font-size: 1rem;
`;

const StyledList = styled.ul`
  font-size: 0.8rem;
  list-style-type: disc;
  padding-left: 1.5rem;
  margin-bottom: 1rem;

  & li {
    padding-bottom: 0.6rem;

    &:last-child {
      padding-bottom: 0;
    }
  }
`;

const DataSource: FC<DataSourceProps> = ({ isFile = true, close }) => {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [url, setURL] = useState<string>('');
  const [isValidFile, setIsValidFile] = useState<boolean>(true);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [originalFileNames, setOriginalFileNames] = useState<string[]>([]);

  const dispatch = useAppDispatch();
  const { files } = useAppSelector(conversationSelector);

  useEffect(() => {
    const originalNames = files.map((file) =>
      extractBetweenDotsWithExtension(file.file_name),
    );
    setOriginalFileNames(originalNames);
  }, [files]);

  const handleFileUpload = async (): Promise<void> => {
    if (file) {
      try {
        close();
        const isDuplicate = originalFileNames.includes(
          extractBetweenDotsWithExtension(file.name),
        );
        if (isDuplicate) {
          notify(t('duplicateFileNotification'), NotificationSeverity.WARNING);
          setFile(null);
          return;
        }
        notify(t('fileUploadStarted'), NotificationSeverity.INFO);
        const response = await dispatch(uploadFile({ file }));
        const { status } = unwrapResult(response);
        if (status === 200) {
          notify(t('fileUploadSuccessful'), NotificationSeverity.SUCCESS);
          dispatch(fetchInitialFiles());
        } else {
          notify(t('filesFailedToUpload'), NotificationSeverity.ERROR);
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
          const { status } = error as {
            status: number;
            message: { detail: string };
          };
          if (status === 404) {
            notify(t('fileNotFound'), NotificationSeverity.ERROR);
          } else if (status === 500) {
            notify(t('serverError'), NotificationSeverity.ERROR);
          } else {
            notify(`${t('filesFailedToUpload')} `, NotificationSeverity.ERROR);
          }
        }
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
      const isDuplicate = originalFileNames.includes(
        extractBetweenDotsWithExtension(selectedFile.name),
      );
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

  const handleURLChange = (event: SyntheticEvent): void => {
    event.preventDefault();
    setURL((event.target as HTMLTextAreaElement).value);
  };

  const handleURLSubmit = async () => {
    const links = url
      .split(';')
      .map((link) => link.trim())
      .filter(Boolean);
    const validLinks = links.filter((link) => isValidUrl(link));
    if (validLinks.length === 0) {
      notify(t('invalidLink'), NotificationSeverity.ERROR);
      return;
    }
    close();
    notify(t('linkUploadStarted'), NotificationSeverity.INFO);
    try {
      await dispatch(submitDataSourceURL({ link_list: validLinks })).unwrap();
      notify(t('linkSubmittedSuccessfully'), NotificationSeverity.SUCCESS);
    } catch {
      notify(t('linkFailedToSubmit'), NotificationSeverity.ERROR);
    } finally {
      setURL('');
    }
  };

  return (
    <DataSourceWrapper data-testid='data-source-wrapper'>
      {isFile ? (
        <FileDataSourceWrapper data-testid='file-data-source-wrapper'>
          <Strong>{t('uploadFile')}</Strong>
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
        </FileDataSourceWrapper>
      ) : (
        <LinkDataSourceWrapper data-testid='link-data-source-wrapper'>
          <Strong className='mt-1'>{t('useLink')}</Strong>
          <StyledList>
            <li>{t('validLinkMessage')}</li>
            <li>{t('multipleURLs')}</li>
          </StyledList>
          <StyledTextInput
            value={url}
            onChange={handleURLChange}
            placeholder={t('pasteLink')}
            id='link-upload'
            type='text'
            labelText=''
            data-testid='add-link-input'
          />
          <StyledModelWrapper>
            <StyledButton
              disabled={!url}
              onClick={handleURLSubmit}
              data-testid='add-link-button'
            >
              {t('add')}
            </StyledButton>
          </StyledModelWrapper>
        </LinkDataSourceWrapper>
      )}
    </DataSourceWrapper>
  );
};

export default DataSource;
