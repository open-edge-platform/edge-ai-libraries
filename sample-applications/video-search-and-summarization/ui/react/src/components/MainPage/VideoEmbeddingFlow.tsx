// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { useState, useRef } from 'react';
import styled from 'styled-components';
import {
  Button,
  ModalBody,
  ModalFooter,
  MultiSelect,
  ProgressBar,
  TextInput,
  Toggletip,
  ToggletipButton,
  ToggletipContent,
} from '@carbon/react';
import { Information } from '@carbon/icons-react';
import { useTranslation } from 'react-i18next';
import { useAppSelector, useAppDispatch } from '../../redux/store';
import { SearchSelector } from '../../redux/search/searchSlice';
import axios from 'axios';
import { useEffect } from 'react';
import { APP_URL } from '../../config';
import { videosLoad } from '../../redux/video/videoSlice';
import { NotificationSeverity, notify } from '../Notification/notify';

const CenteredContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2.5rem;
  width: 100%;
`;

const DropArea = styled.div<{ dragging: boolean }>`
  border: 2.5px dashed #0072c3;
  border-radius: 16px;
  padding: 2.5rem 5rem;
  background: ${({ dragging }) => (dragging ? '#e5f6ff' : '#fafdff')};
  color: #0072c3;
  text-align: center;
  cursor: pointer;
  font-size: 1.15rem;
  font-weight: 500;
  box-shadow: 0 2px 16px rgba(0, 114, 195, 0.07);
  transition: background 0.2s, box-shadow 0.2s;
  &:hover {
    background: #e5f6ff;
    box-shadow: 0 4px 24px rgba(0, 114, 195, 0.12);
  }
`;

const Stepper = styled.div`
  display: flex;
  flex-direction: row;
  gap: 1.5rem;
  margin-bottom: 2.5rem;
  justify-content: center;
  align-items: center;
`;

const Step = styled.div<{ active: boolean }>`
  padding: 0.7rem 2.2rem;
  border-radius: 8px;
  background: ${({ active }) => (active ? 'var(--color-info)' : '#e0e0e0')};
  color: ${({ active }) => (active ? 'var(--color-white)' : '#333')};
  font-weight: ${({ active }) => (active ? 'bold' : 'normal')};
  font-size: 1.1rem;
  box-shadow: ${({ active }) => (active ? '0 2px 12px rgba(0,114,195,0.10)' : 'none')};
  transition: background 0.2s, color 0.2s;
`;

const MainButton = styled(Button)`
  min-width: 280px;
  font-size: 1.15rem;
  font-weight: 600;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,114,195,0.08);
  padding: 0.8rem 2rem;
  margin-top: 1.5rem;
  background: var(--color-info);
  color: var(--color-white);
  &:hover {
    background: #005fa3;
    color: var(--color-white);
    box-shadow: 0 4px 16px rgba(0,114,195,0.14);
  }
  &:active {
    background: #003d66;
    color: var(--color-white);
  }
  &:disabled {
    background: #e0e0e0;
    color: #aaa;
    cursor: not-allowed;
  }
`;

const SettingsPanel = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1.2rem;
  width: 100%;
  padding-bottom: 2rem;
  overflow-y: auto;
  max-height: 70vh;
`;

const StyledModalFooter = styled(ModalFooter)`
  padding: 1.5rem 0 0 0 !important;
  margin: 0 -1rem -1rem -1rem !important;
  z-index: 10 !important;
  position: relative !important;
`;

export interface VideoEmbeddingFlowProps {
  onClose?: () => void;
}

export default function VideoEmbeddingFlow({ onClose }: VideoEmbeddingFlowProps) {
  const { t } = useTranslation();
  const dispatch = useAppDispatch();

  // API endpoints
  const videoUploadAPi = `${APP_URL}/videos`;

  // State
  const [step, setStep] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [processing, setProcessing] = useState<boolean>(false);
  const [progressText, setProgressText] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [videoTags, setVideoTags] = useState<string | null>('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);

  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Get suggested tags from Redux store
  const { suggestedTags } = useAppSelector(SearchSelector);

  useEffect(() => {
    if (!uploading) {
      resetForm();
    }
  }, []);

  const resetForm = () => {
    setSelectedFile(null);
    setVideoTags('');
    setSelectedTags([]);
    setProgressText('');
    setUploadProgress(0);
    setUploading(false);
    setProcessing(false);
    setStep(0);
  };

  const handleFileSelect = (files: FileList | null) => {
    if (files && files.length > 0) {
      setSelectedFile(files[0]);
    }
  };

  const uploadVideo = async (videoData: any) => {
    const formData = new FormData();

    if (selectedFile) {
      formData.append('video', selectedFile);
    }

    if (videoData.tags) {
      formData.append('tags', videoData.tags);
    }

    try {
      return await axios.post(videoUploadAPi, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (ev: any) => {
          setUploadProgress((ev.progress ?? 0) * 100);
        },
      });
    } catch (error) {
      if (axios.isAxiosError(error)) {
        throw new Error(`Video upload failed: ${error.response?.data?.message || error.message}`);
      }
      throw error;
    }
  };

  const triggerEmbeddings = async (videoId: string) => {
    const api = [videoUploadAPi, 'search-embeddings', videoId].join('/');
    try {
      const res = await axios.post<{ status: string; message: string }>(api);
      return res.data;
    } catch (error) {
      if (axios.isAxiosError(error)) {
        throw new Error(`Embedding creation failed: ${error.response?.data?.message || error.message}`);
      }
      throw error;
    }
  };

  const triggerCreateEmbedding = async () => {
    try {
      setUploading(true);
      setProgressText(t('uploadingVideo'));

      const videoData: any = {};
      const tags = [];

      if (videoTags) {
        tags.push(...videoTags.split(',').map((tag) => tag.trim()));
      }

      if (selectedTags && selectedTags.length > 0) {
        tags.push(...selectedTags.map((tag) => tag.trim()));
      }

      if (tags.length > 0) {
        videoData.tags = tags.join(',');
      }

      const videoRes = await uploadVideo(videoData);
      dispatch(videosLoad());
      setUploading(false);
      setProcessing(true);

      if (videoRes.data.videoId) {
        setProgressText(t('CreatingEmbeddings'));

        const embeddingRes = await triggerEmbeddings(videoRes.data.videoId);

        if (embeddingRes.status === 'success') {
          setProgressText(t('allDone'));
          setUploading(false);
          resetForm();
          notify(t('CreatingEmbeddings') + ' ' + t('success'), NotificationSeverity.SUCCESS);
          if (onClose) {
            onClose();
          }
        } else {
          throw new Error(embeddingRes.message || t('unknownError'));
        }
      } else {
        throw new Error(t('serverError'));
      }
    } catch (error: unknown) {
      console.error('Video upload/processing error:', error);
      setUploading(false);
      setProcessing(false);

      let errorMessage = t('videoUploadError');

      if (axios.isAxiosError(error) && error.response?.data?.message) {
        errorMessage = error.response.data.message;
      } else if (error instanceof Error) {
        errorMessage = error.message;
      }

      notify(errorMessage, NotificationSeverity.ERROR);
      setProgressText('');
    }
  };

  return (
    <>
      <ModalBody>
        <CenteredContainer>
          <Stepper>
            <Step active={step === 0}>{t('SelectVideo')}</Step>
            <Step active={step === 1}>{t('Set Parameter')}</Step>
          </Stepper>

          {step === 0 && (
            <DropArea
              dragging={dragging}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={e => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={e => {
                e.preventDefault();
                setDragging(false);
                handleFileSelect(e.dataTransfer.files);
              }}
            >
              {selectedFile ? (
                <>
                  <h3 style={{ fontWeight: 600, fontSize: '1.2rem', marginBottom: '0.5rem' }}>
                    {selectedFile.name}
                  </h3>
                  <MainButton kind="tertiary" onClick={() => {
                    setSelectedFile(null);
                  }}>
                    {t('changeVideo')}
                  </MainButton>
                </>
              ) : (
                <>
                  <div style={{ fontWeight: 500 }}>{t('SelectVideo') || 'Select a Video'}</div>
                  <div style={{ fontSize: '0.95rem', color: '#666', marginTop: '0.5rem' }}>
                    or drag and drop here
                  </div>
                </>
              )}
              <input
                type="file"
                accept=".mp4"
                style={{ display: 'none' }}
                ref={fileInputRef}
                onChange={e => handleFileSelect(e.target.files)}
              />
            </DropArea>
          )}

          {step === 1 && (
            <>
              <SettingsPanel>
                {suggestedTags && suggestedTags.length > 0 && (
                  <MultiSelect
                    items={suggestedTags}
                    itemToString={(item) => (item ? item : '')}
                    onChange={(data) => {
                      if (data.selectedItems) {
                        setSelectedTags(data.selectedItems);
                      }
                    }}
                    id='availabel-tags-selector'
                    label={t('availableVideoTags')}
                  />
                )}
                <TextInput
                  labelText={
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      {t('customVideoTags')}
                      <Toggletip>
                        <ToggletipButton>
                          <Information />
                        </ToggletipButton>
                        <ToggletipContent>
                          {t('videoTagsinfo')}
                        </ToggletipContent>
                      </Toggletip>
                    </span>
                  }
                  onChange={(ev) => {
                    setVideoTags(ev.currentTarget.value);
                  }}
                  id='videoTags'
                  value={videoTags || ''}
                />
              </SettingsPanel>

              {uploading && (
                <ProgressBar value={uploadProgress} helperText={uploadProgress.toFixed(2) + '%'} label={progressText} />
              )}
              {processing && <ProgressBar label={progressText} />}
            </>
          )}
        </CenteredContainer>
      </ModalBody>
      <StyledModalFooter>
        {step === 0 ? (
          <>
            <Button
              kind="secondary"
              onClick={() => {
                resetForm();
                if (onClose) {
                  onClose();
                }
              }}
            >
              {t('cancel')}
            </Button>
            <Button
              kind="primary"
              disabled={!selectedFile}
              onClick={() => setStep(1)}
            >
              Next
            </Button>
          </>
        ) : (
          <>
            <Button kind="secondary" disabled={uploading || processing} onClick={() => setStep(0)}>
              Back
            </Button>
            <Button
              kind="primary"
              disabled={uploading || !selectedFile}
              onClick={triggerCreateEmbedding}
            >
              {uploading ? t('uploadingVideoState') : t('CreateVideoEmbedding')}
            </Button>
          </>
        )}
      </StyledModalFooter>
    </>
  );
}