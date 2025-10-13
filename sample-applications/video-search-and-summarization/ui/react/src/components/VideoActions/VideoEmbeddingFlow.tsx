// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Fragment, useState, useRef, useEffect, useCallback, useMemo } from 'react';
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
import type { AxiosProgressEvent } from 'axios';
import { APP_URL } from '../../config';
import { videosLoad } from '../../redux/video/videoSlice';
import { NotificationSeverity, notify } from '../Notification/notify';

const CenteredContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  width: 100%;
  padding-bottom: 0.5rem;
`;

const DropArea = styled.div<{ dragging: boolean }>`
  border: 2.5px dashed #0072c3;
  border-radius: 0px;
  padding: 2rem 3.5rem;
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

const TimelineContainer = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 1.75rem;
  width: 100%;
  max-width: 720px;
  gap: 0.5rem;
  padding: 0 0.5rem;
`;

const TimelineStep = styled.div<{ active: boolean; completed: boolean }>`
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1 1 0;
  min-width: 120px;
  max-width: 200px;
  padding: 0 0.75rem;
`;

const TimelineCircle = styled.div<{ active: boolean; completed: boolean }>`
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: ${({ active, completed }) =>
    active ? 'var(--color-info)' : completed ? '#0072c3' : '#e0e0e0'};
  color: ${({ active, completed }) =>
    active || completed ? 'var(--color-white)' : '#333'};
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 1rem;
  z-index: 2;
  border: 2px solid ${({ active }) => (active ? '#005fa3' : 'transparent')};
  transition: all 0.2s ease;
`;

const TimelineLabel = styled.div<{ active: boolean }>`
  margin-top: 0.5rem;
  font-size: 1rem;
  color: ${({ active }) => (active ? 'var(--color-info)' : '#333')};
  font-weight: ${({ active }) => (active ? 'bold' : 'normal')};
  text-align: center;
  max-width: 8rem;
`;

const TimelineConnector = styled.div<{ completed: boolean }>`
  flex: 1 1 0;
  max-width: 160px;
  height: 4px;
  background: ${({ completed }) => (completed ? '#0072c3' : '#e0e0e0')};
  transition: background 0.2s ease;
  align-self: center;
  border-radius: 2px;
`;

const MainButton = styled(Button)`
  min-width: 280px;
  font-size: 1.15rem;
  font-weight: 600;
  border-radius: 0px;
  box-shadow: 0 2px 8px rgba(0,114,195,0.08);
  padding: 0.8rem 2rem;
  margin-top: 1.5rem;
  background: var(--color-info);
  color: var(--color-white);
  display: flex;
  justify-content: center;
  align-items: center;
  text-align: center;
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
  padding-bottom: 1rem;
  overflow-y: auto;
  max-height: 50vh;
`;

const StyledModalFooter = styled(ModalFooter)`
  padding: 0rem 0 0 0 !important;
  margin: 0 -1rem -1rem -1rem !important;
  z-index: 10 !important;
  position: relative !important;

  button {
    font-size: 1.1rem;
    display: flex;
    justify-content: center;
    align-items: center;
    text-align: center;
  }
`;

const VideoPreviewContainer = styled.div`
  width: 100%;
  max-width: 320px;
  margin: 0.75rem auto;
  background: var(--color-black);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
`;

const StyledVideoPlayer = styled.video`
  width: 100%;
  height: auto;
  max-height: 180px;
  display: block;
  background: var(--color-black);
`;

export interface VideoEmbeddingFlowProps {
  onClose?: () => void;
}

type VideoUploadPayload = {
  tags?: string;
};

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
  const [videoPreviewUrl, setVideoPreviewUrl] = useState<string | null>(null);

  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoPreviewUrlRef = useRef<string | null>(null);

  // Get suggested tags from Redux store
  const { suggestedTags } = useAppSelector(SearchSelector);

  const displayFileName = useMemo(() => {
    if (!selectedFile) return '';
    const originalName = selectedFile.name;
    return originalName.toLowerCase().endsWith('.mp4')
      ? originalName.slice(0, -4)
      : originalName;
  }, [selectedFile]);

  const resetForm = useCallback(() => {
    // Clean up video preview URL first
    if (videoPreviewUrlRef.current) {
      URL.revokeObjectURL(videoPreviewUrlRef.current);
      videoPreviewUrlRef.current = null;
    }
    setVideoPreviewUrl(null);
    setSelectedFile(null);
    setVideoTags('');
    setSelectedTags([]);
    setProgressText('');
    setUploadProgress(0);
    setUploading(false);
    setProcessing(false);
    setStep(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, []); // Empty dependency array - stable reference

  useEffect(() => {
    resetForm();
  }, [resetForm]);

  // Cleanup video preview URL on unmount
  useEffect(() => {
    return () => {
      if (videoPreviewUrlRef.current) {
        URL.revokeObjectURL(videoPreviewUrlRef.current);
      }
    };
  }, []);

  const timelineSteps = useMemo(
    () => [t('SelectVideo'), t('Set Parameter'), t('ReviewAndCreate')],
    [t]
  );

  const handleFileSelect = (files: FileList | null) => {
    if (files && files.length > 0) {
      // Clean up previous preview URL if exists
      if (videoPreviewUrlRef.current) {
        URL.revokeObjectURL(videoPreviewUrlRef.current);
      }
      const file = files[0];
      setSelectedFile(file);
      // Create a preview URL for the video
      const previewUrl = URL.createObjectURL(file);
      videoPreviewUrlRef.current = previewUrl;
      setVideoPreviewUrl(previewUrl);
    }
  };

  const uploadVideo = async (videoData: VideoUploadPayload) => {
    const formData = new FormData();

    if (selectedFile) {
      formData.append('video', selectedFile);
    }

    if (videoData.tags) {
      formData.append('tags', videoData.tags);
    }

    try {
      return await axios.post<{ videoId?: string }>(videoUploadAPi, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (event: AxiosProgressEvent) => {
          setUploadProgress((event.progress ?? 0) * 100);
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

      const videoData: VideoUploadPayload = {};
      const tags: string[] = [];

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
          <TimelineContainer>
            {timelineSteps.map((label, idx, arr) => {
              const isActive = step === idx;
              const isCompleted = step > idx;
              return (
                <Fragment key={label}>
                  <TimelineStep active={isActive} completed={isCompleted}>
                    <TimelineCircle active={isActive} completed={isCompleted}>
                      {idx + 1}
                    </TimelineCircle>
                    <TimelineLabel active={isActive}>{label}</TimelineLabel>
                  </TimelineStep>
                  {idx < arr.length - 1 && <TimelineConnector completed={step > idx} />}
                </Fragment>
              );
            })}
          </TimelineContainer>

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
                    {displayFileName}
                  </h3>
                  <MainButton 
                    kind="tertiary" 
                    style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', margin: '0 auto' }}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (videoPreviewUrlRef.current) {
                        URL.revokeObjectURL(videoPreviewUrlRef.current);
                        videoPreviewUrlRef.current = null;
                      }
                      setVideoPreviewUrl(null);
                      setSelectedFile(null);
                      if (fileInputRef.current) {
                        fileInputRef.current.value = '';
                        // Open file picker after clearing
                        setTimeout(() => {
                          fileInputRef.current?.click();
                        }, 0);
                      }
                    }}
                  >
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
                    key={`tags-${selectedTags.join('-')}`}
                    items={suggestedTags}
                    itemToString={(item) => (item ? item : '')}
                    initialSelectedItems={selectedTags}
                    onChange={(data) => {
                      if (data.selectedItems) {
                        setSelectedTags(data.selectedItems);
                      }
                    }}
                    id='availabel-tags-selector'
                    label={t('availableVideoTags')}
                    sortItems={() => suggestedTags}
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

          {step === 2 && (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                textAlign: 'center',
                gap: '1.5rem',
                width: '100%',
                padding: '0 0 0.5rem',
              }}
            >
              <div
                style={{
                  background: '#f4f4f4',
                  border: '1px solid #e0e0e0',
                  borderRadius: '8px',
                  padding: '1.25rem 1.75rem',
                  textAlign: 'left',
                  maxWidth: '540px',
                  width: '100%',
                }}
              >
                {/* Video Preview inside the details box */}
                {videoPreviewUrl && (
                  <VideoPreviewContainer>
                    <StyledVideoPlayer controls>
                      <source src={videoPreviewUrl} type="video/mp4" />
                      Your browser does not support the video tag.
                    </StyledVideoPlayer>
                  </VideoPreviewContainer>
                )}
                
                <div style={{ marginTop: videoPreviewUrl ? '1rem' : '0' }}>
                  <div>
                    <strong>{t('videoNameLabel')}:</strong> {selectedFile ? displayFileName : '-'}
                  </div>
                  {videoTags && videoTags.trim().length > 0 && (
                    <div>
                      <strong>{t('customVideoTags')}:</strong> {videoTags}
                    </div>
                  )}
                </div>
              </div>
              {uploading && (
                <ProgressBar value={uploadProgress} helperText={uploadProgress.toFixed(2) + '%'} label={progressText} />
              )}
              {processing && <ProgressBar label={progressText} />}
            </div>
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
        ) : step === 1 ? (
          <>
            <Button kind="secondary" disabled={uploading || processing} onClick={() => setStep(0)}>
              Back
            </Button>
            <Button
              kind="primary"
              disabled={uploading || !selectedFile}
              onClick={() => setStep(2)}
            >
              Next
            </Button>
          </>
        ) : (
          <>
            <Button kind="secondary" disabled={uploading || processing} onClick={() => setStep(1)}>
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