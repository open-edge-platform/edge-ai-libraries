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
import { videosLoad, videosSelector } from '../../redux/video/videoSlice';
import { Video } from '../../redux/video/video';
import axios from 'axios';
import type { AxiosProgressEvent } from 'axios';
import { APP_URL, ASSETS_ENDPOINT } from '../../config';
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

const VideoSelectorContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  width: 100%;
  margin-top: 0.5rem;
`;

const VideoSelectorDivider = styled.div`
  display: flex;
  align-items: center;
  gap: 1rem;
  margin: 0.25rem 0;
  color: #666;
  font-size: 0.9rem;
  
  &::before,
  &::after {
    content: '';
    flex: 1;
    height: 1px;
    background: #e0e0e0;
  }
`;

const RecentVideosList = styled.div`
  display: flex;
  flex-direction: row;
  gap: 0.75rem;
  padding: 0.5rem;
  background: #fafafa;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  width: 100%;
`;

const RecentVideoItem = styled.div<{ selected: boolean }>`
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 0 0 calc(20% - 0.6rem);
  min-width: 120px;
  padding: 0.5rem;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: ${({ selected }) => (selected ? '#e5f6ff' : '#fff')};
  border: 2px solid ${({ selected }) => (selected ? '#0072c3' : '#e0e0e0')};
  
  &:hover {
    background: ${({ selected }) => (selected ? '#e5f6ff' : '#f0f0f0')};
    border-color: #0072c3;
  }
`;

const VideoItemInfo = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  width: 100%;
  text-align: center;
  margin-top: 0.5rem;
`;

const VideoItemName = styled.span`
  font-weight: 500;
  color: #333;
  font-size: 0.8rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  width: 100%;
`;

const VideoItemDate = styled.span`
  font-size: 0.65rem;
  color: #666;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  width: 100%;
`;

const VideoThumbnail = styled.video`
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  border-radius: 4px;
  background: #000;
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

const ErrorBox = styled.div`
  background-color: #f8d7da;
  color: #721c24;
  padding: 1rem;
  font-size: 0.9rem;
`;

const CodePara = styled.p`
  font-family: monospace;
  background: #f5f5f5;
  padding: 0.5rem;
  margin-top: 0.5rem;
  font-size: 0.85rem;
  color: #333;
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

  // Get videos from Redux store
  const { videos } = useAppSelector(videosSelector);

  // Get top 5 recent videos sorted by upload date
  const recentVideos = useMemo(() => {
    return [...videos]
      .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
      .slice(0, 5);
  }, [videos]);

  // State
  const [step, setStep] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [processing, setProcessing] = useState<boolean>(false);
  const [progressText, setProgressText] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedExistingVideo, setSelectedExistingVideo] = useState<Video | null>(null);
  const [formatError, setFormatError] = useState<string | null>(null);
  const [videoTags, setVideoTags] = useState<string | null>('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [videoPreviewUrl, setVideoPreviewUrl] = useState<string | null>(null);
  const [uploadErrorMessage, setUploadErrorMessage] = useState<string | null>(null);

  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoPreviewUrlRef = useRef<string | null>(null);

  // Get suggested tags from Redux store
  const { suggestedTags } = useAppSelector(SearchSelector);

  const displayFileName = useMemo(() => {
    if (selectedExistingVideo) {
      const name = selectedExistingVideo.dataStore?.fileName || selectedExistingVideo.name || selectedExistingVideo.videoId;
      return name.toLowerCase().endsWith('.mp4') ? name.slice(0, -4) : name;
    }
    if (!selectedFile) return '';
    const originalName = selectedFile.name;
    return originalName.toLowerCase().endsWith('.mp4')
      ? originalName.slice(0, -4)
      : originalName;
  }, [selectedFile, selectedExistingVideo]);

  const resetForm = useCallback(() => {
    // Clean up video preview URL first
    if (videoPreviewUrlRef.current) {
      URL.revokeObjectURL(videoPreviewUrlRef.current);
      videoPreviewUrlRef.current = null;
    }
    setVideoPreviewUrl(null);
    setSelectedFile(null);
    setSelectedExistingVideo(null);
    setFormatError(null);
    setVideoTags('');
    setSelectedTags([]);
    setProgressText('');
    setUploadProgress(0);
    setUploading(false);
    setProcessing(false);
    setUploadErrorMessage(null);
    setStep(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    // Load videos list for the selector
    dispatch(videosLoad());
  }, [dispatch]);

  const clearErrorState = useCallback(() => {
    setUploadErrorMessage(null);
    setUploadProgress(0);
    setProgressText('');
  }, []);

  useEffect(() => {
    resetForm();
  }, [resetForm]);

  useEffect(() => {
    if (step !== 2) {
      clearErrorState();
    }
  }, [step, clearErrorState]);

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

  const findAtom = (buffer: Uint8Array, atomType: string): number => {
    const atomBytes = new TextEncoder().encode(atomType);
    for (let i = 0; i < buffer.length - 4; i++) {
      if (
        buffer[i] === atomBytes[0] &&
        buffer[i + 1] === atomBytes[1] &&
        buffer[i + 2] === atomBytes[2] &&
        buffer[i + 3] === atomBytes[3]
      ) {
        return i;
      }
    }
    return -1;
  };

  const isStreamable = async (file: File): Promise<boolean> => {
    try {
      const arrayBuffer = await file.arrayBuffer();
      const buffer = new Uint8Array(arrayBuffer);

      const moovIndex = findAtom(buffer, 'moov');
      const mdatIndex = findAtom(buffer, 'mdat');

      // If either atom is missing, treat as not streamable
      if (moovIndex === -1 || mdatIndex === -1) return false;

      return moovIndex < mdatIndex;
    } catch (error) {
      console.error('Error checking streamability:', error);
      return false;
    }
  };

  const handleFileSelect = async (files: FileList | null) => {
    if (files && files.length > 0) {
      const file = files[0];
      
      // Validate file format
      const fileName = file.name.toLowerCase();
      const fileType = file.type;
      
      if (!fileName.endsWith('.mp4') && fileType !== 'video/mp4') {
        setFormatError(t('invalidVideoFormat'));
        setSelectedFile(null);
        setVideoPreviewUrl(null);
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
        return;
      }
      
      // Check if MP4 is streamable
      try {
        const streamable = await isStreamable(file);
        if (!streamable) {
          setFormatError(t('OnlyStreamableMp4'));
          setSelectedFile(null);
          setVideoPreviewUrl(null);
          if (fileInputRef.current) {
            fileInputRef.current.value = '';
          }
          return;
        }
      } catch (error) {
        console.error('Error checking streamability:', error);
      }
      
      // Clear previous errors
      setFormatError(null);
      
      // Clean up previous preview URL if exists
      if (videoPreviewUrlRef.current) {
        URL.revokeObjectURL(videoPreviewUrlRef.current);
      }
      
      setSelectedFile(file);
      // Clear existing video selection when a new file is selected
      setSelectedExistingVideo(null);
      const previewUrl = URL.createObjectURL(file);
      videoPreviewUrlRef.current = previewUrl;
      setVideoPreviewUrl(previewUrl);
    }
  };

  // Handler for selecting an existing video
  const handleSelectExistingVideo = (video: Video) => {
    if (videoPreviewUrlRef.current) {
      URL.revokeObjectURL(videoPreviewUrlRef.current);
      videoPreviewUrlRef.current = null;
    }
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    setFormatError(null);
    setSelectedExistingVideo(video);
    if (video.dataStore) {
      const existingVideoUrl = `${ASSETS_ENDPOINT}/${video.dataStore.bucket}/${video.url}`;
      setVideoPreviewUrl(existingVideoUrl);
    } else {
      setVideoPreviewUrl(null);
    }
    if (video.tags && video.tags.length > 0) {
      setSelectedTags(video.tags);
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
        const responseMessage = error.response?.data?.message;
        const status = error.response?.status;
        const timeoutHit =
          error.code === 'ECONNABORTED' ||
          status === 504 ||
          /timeout/i.test(responseMessage || error.message || '');

        if (timeoutHit || responseMessage === 'Internal server error') {
          throw new Error(t('timeoutError'));
        }

        throw new Error(responseMessage || error.message);
      }
      throw error;
    }
  };

  const triggerCreateEmbedding = async () => {
    try {
      let videoIdToUse: string | undefined;

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

      // Check if using existing video or uploading new one
      if (selectedExistingVideo) {
        // Use existing video - skip upload
        setProcessing(true);
        setProgressText(t('CreatingEmbeddings'));
        videoIdToUse = selectedExistingVideo.videoId;
      } else {
        // Upload new video
        setUploading(true);
        setProgressText(t('uploadingVideo'));

        const videoRes = await uploadVideo(videoData);
        dispatch(videosLoad());
        setUploading(false);
        setProcessing(true);

        if (videoRes.data.videoId) {
          videoIdToUse = videoRes.data.videoId;
        } else {
          throw new Error(t('serverError'));
        }
      }

      setProgressText(t('CreatingEmbeddings'));
      const embeddingRes = await triggerEmbeddings(videoIdToUse);

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
    } catch (error: unknown) {
      console.error('Video upload/processing error:', error);
      setUploading(false);
      setProcessing(false);

      let errorMessage = t('videoUploadError');

      if (axios.isAxiosError(error)) {
        const responseMessage = error.response?.data?.message;
        const status = error.response?.status;
        const timeoutHit =
          error.code === 'ECONNABORTED' ||
          status === 504 ||
          /timeout/i.test(responseMessage || error.message || '');

        if (timeoutHit || responseMessage === 'Internal server error') {
          errorMessage = t('timeoutError');
        } else if (responseMessage) {
          errorMessage = responseMessage;
        } else if (error.message) {
          errorMessage = error.message;
        }
      } else if (error instanceof Error) {
        if (/Embedding creation failed: Internal server error/i.test(error.message)) {
          errorMessage = t('timeoutError');
        } else {
        errorMessage = error.message;
        }
      }

      setUploadErrorMessage(errorMessage);
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
            <>
              {/* Show selected existing video if one is selected */}
              {selectedExistingVideo && !selectedFile && (
                <div style={{
                  background: '#e5f6ff',
                  border: '2px solid #0072c3',
                  borderRadius: '8px',
                  padding: '1.5rem',
                  textAlign: 'center',
                  marginBottom: '1rem'
                }}>
                  <h3 style={{ fontWeight: 600, fontSize: '1.2rem', marginBottom: '0.5rem', color: '#0072c3' }}>
                    {t('selectedVideo')}: {selectedExistingVideo.dataStore?.fileName || selectedExistingVideo.name || selectedExistingVideo.videoId}
                  </h3>
                  <div style={{ fontSize: '0.9rem', color: '#666', marginBottom: '0.75rem' }}>
                    {t('uploadedOn')}: {new Date(selectedExistingVideo.createdAt).toLocaleString()}
                  </div>
                  <MainButton 
                    kind="tertiary" 
                    style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', margin: '0 auto' }}
                    onClick={() => {
                      setSelectedExistingVideo(null);
                      setSelectedTags([]);
                    }}
                  >
                    {t('changeVideo')}
                  </MainButton>
                </div>
              )}
              
              {/* Upload new video area - only show when no existing video is selected */}
              {!selectedExistingVideo && (
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
                      <div style={{ fontWeight: 500 }}>{t('uploadNew') || 'Upload New Video'}</div>
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

              {/* Recent videos selector - only show when no file is selected and there are recent videos */}
              {!selectedFile && recentVideos.length > 0 && (
                <VideoSelectorContainer>
                  <VideoSelectorDivider>{t('orSelectExisting')}</VideoSelectorDivider>
                  <RecentVideosList>
                    {recentVideos.map((video) => (
                      <RecentVideoItem
                        key={video.videoId}
                        selected={selectedExistingVideo?.videoId === video.videoId}
                        onClick={() => handleSelectExistingVideo(video)}
                      >
                        {video.dataStore && (
                          <VideoThumbnail
                            src={`${ASSETS_ENDPOINT}/${video.dataStore.bucket}/${video.url}`}
                            muted
                            preload="metadata"
                            onMouseEnter={(e) => (e.currentTarget as HTMLVideoElement).play()}
                            onMouseLeave={(e) => {
                              const el = e.currentTarget as HTMLVideoElement;
                              el.pause();
                              el.currentTime = 0;
                            }}
                          />
                        )}
                        <VideoItemInfo>
                          <VideoItemName title={video.dataStore?.fileName || video.name || video.videoId}>
                            {video.dataStore?.fileName || video.name || video.videoId}
                          </VideoItemName>
                          <VideoItemDate title={new Date(video.createdAt).toLocaleString()}>
                            {new Date(video.createdAt).toLocaleDateString()}
                          </VideoItemDate>
                        </VideoItemInfo>
                      </RecentVideoItem>
                    ))}
                  </RecentVideosList>
                </VideoSelectorContainer>
              )}
            </>
          )}
          {formatError && (
            formatError === t('OnlyStreamableMp4') ? (
              <ErrorBox style={{ maxWidth: '800px', width: '100%', margin: '0 auto', textAlign: 'center', border: '2px solid #f5c6cb' }}>
                <div style={{ fontSize: '1.1rem' }}><strong>{t('OnlyStreamableMp4')}</strong></div>
                <div style={{ fontSize: '1.0rem', marginTop: '0.5rem' }}>{t('StreamableHelpText')}</div>
                  <CodePara>ffmpeg -i &lt;input mp4 video&gt; -c copy -map 0 -movflags +faststart &lt;output mp4 video&gt;</CodePara>
              </ErrorBox>
            ) : (
              <ErrorBox style={{ maxWidth: '800px', width: '100%', margin: '0 auto', textAlign: 'center', border: '2px solid #f5c6cb' }}>
                <div><strong>{formatError}</strong></div>
              </ErrorBox>
            )
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
                    <strong>{t('videoNameLabel')}:</strong> {displayFileName || '-'}
                  </div>
                  {selectedExistingVideo && (
                    <div>
                      <strong>{t('uploadedOn')}:</strong> {new Date(selectedExistingVideo.createdAt).toLocaleString()}
                    </div>
                  )}
                  {videoTags && videoTags.trim().length > 0 && (
                    <div>
                      <strong>{t('customVideoTags')}:</strong> {videoTags}
                    </div>
                  )}
                </div>
              </div>
              {uploadErrorMessage && (
                uploadErrorMessage === t('OnlyStreamableMp4') ? (
                  <ErrorBox style={{ maxWidth: '800px', width: '100%', margin: '0 auto', textAlign: 'center', border: '2px solid #f5c6cb' }}>
                    <div style={{ fontSize: '1.1rem' }}><strong>{t('OnlyStreamableMp4')}</strong></div>
                    <div style={{ fontSize: '1.0rem', marginTop: '0.5rem' }}>{t('StreamableHelpText')}</div>
                    <CodePara>ffmpeg -i &lt;input mp4 video&gt; -c copy -map 0 -movflags +faststart &lt;output mp4 video&gt;</CodePara>
                  </ErrorBox>
                ) : (
                  <ErrorBox style={{ maxWidth: '800px', width: '100%', margin: '0 auto', textAlign: 'center', border: '2px solid #f5c6cb' }}>
                    <div><strong>{uploadErrorMessage}</strong></div>
                  </ErrorBox>
                )
              )}
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
              disabled={!selectedFile && !selectedExistingVideo}
              onClick={() => setStep(1)}
            >
              Next
            </Button>
          </>
        ) : step === 1 ? (
          <>
            <Button kind="secondary" disabled={uploading || processing} onClick={() => {
              clearErrorState();
              setStep(0);
            }}>
              Back
            </Button>
            <Button
              kind="primary"
              disabled={uploading || (!selectedFile && !selectedExistingVideo)}
              onClick={() => {
                clearErrorState();
                setStep(2);
              }}
            >
              Next
            </Button>
          </>
        ) : (
          <>
            <Button kind="secondary" disabled={uploading || processing} onClick={() => {
              clearErrorState();
              setStep(1);
            }}>
              Back
            </Button>
            <Button
              kind="primary"
              disabled={uploading || (!selectedFile && !selectedExistingVideo)}
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