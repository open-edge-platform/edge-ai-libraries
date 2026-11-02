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
import { LoadTags, SearchSelector } from '../../redux/search/searchSlice';
import { videosLoad, videosSelector } from '../../redux/video/videoSlice';
import { Video } from '../../redux/video/video';
import axios from 'axios';
import type { AxiosProgressEvent } from 'axios';
import type { MouseEvent } from 'react';
import { APP_URL, ASSETS_ENDPOINT } from '../../config';
import { NotificationSeverity, notify } from '../Notification/notify';
import { getSafePreviewVideoUrl } from '../../utils/util';

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
  overflow-x: visible;
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

interface BatchSubmitResponse {
  job_id: string;
  accepted: number;
  status?: string;
  message?: string;
}

interface BatchItemResult {
  identifier: string;
  video_id?: string;
  status: string;
  message?: string;
  embeddings_count?: number;
}

interface BatchJobStatus {
  job_id: string;
  state: string;
  total: number;
  completed: number;
  failed: number;
  items: BatchItemResult[];
}

// How often to poll a batch embeddings job for progress.
const BATCH_POLL_INTERVAL_MS = 2000;

export default function VideoEmbeddingFlow({ onClose }: VideoEmbeddingFlowProps) {
  const { t } = useTranslation();
  const dispatch = useAppDispatch();

  const createLabelWithTooltip = (label: string, tooltipContent: string) => (
    <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      {label}
      <Toggletip autoAlign>
        <ToggletipButton label={t('info')}>
          <Information />
        </ToggletipButton>
        <ToggletipContent>{tooltipContent}</ToggletipContent>
      </Toggletip>
    </span>
  );

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
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [selectedExistingVideo, setSelectedExistingVideo] = useState<Video | null>(null);
  const [formatError, setFormatError] = useState<string | null>(null);
  const [videoTags, setVideoTags] = useState<string | null>('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [videoPreviewUrl, setVideoPreviewUrl] = useState<string | null>(null);
  const [uploadErrorMessage, setUploadErrorMessage] = useState<string | null>(null);

  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoPreviewUrlRef = useRef<string | null>(null);

  // The first selected file drives the single-video preview and name displays.
  const primaryFile = selectedFiles.length > 0 ? selectedFiles[0] : null;

  // Get suggested tags from Redux store
  const { suggestedTags } = useAppSelector(SearchSelector);

  const displayFileName = useMemo(() => {
    if (selectedExistingVideo) {
      const name = selectedExistingVideo.dataStore?.fileName || selectedExistingVideo.name || selectedExistingVideo.videoId;
      return name.toLowerCase().endsWith('.mp4') ? name.slice(0, -4) : name;
    }
    if (!primaryFile) return '';
    const originalName = primaryFile.name;
    return originalName.toLowerCase().endsWith('.mp4')
      ? originalName.slice(0, -4)
      : originalName;
  }, [primaryFile, selectedExistingVideo]);

  const safeVideoPreviewUrl = useMemo(
    () => getSafePreviewVideoUrl(videoPreviewUrl, ASSETS_ENDPOINT),
    [videoPreviewUrl]
  );
  const encodedSafeVideoPreviewUrl = useMemo(
    () => (safeVideoPreviewUrl ? encodeURI(safeVideoPreviewUrl) : null),
    [safeVideoPreviewUrl]
  );

  const buildSafeAssetVideoUrl = useCallback((video: Video): string | null => {
    const bucket = video.dataStore?.bucket?.trim();
    const objectPath = video.url?.trim();

    if (!bucket || !objectPath) {
      return null;
    }

    if (!/^[a-zA-Z0-9._-]+$/.test(bucket)) {
      return null;
    }

    const encodedPath = objectPath
      .split('/')
      .filter(Boolean)
      .map((segment) => encodeURIComponent(segment))
      .join('/');

    if (!encodedPath) {
      return null;
    }

    const base = ASSETS_ENDPOINT.replace(/\/$/, '');
    const assetVideoUrl = `${base}/${bucket}/${encodedPath}`;
    return getSafePreviewVideoUrl(assetVideoUrl, ASSETS_ENDPOINT);
  }, []);

  const resetForm = useCallback(() => {
    // Clean up video preview URL first
    if (videoPreviewUrlRef.current) {
      URL.revokeObjectURL(videoPreviewUrlRef.current);
      videoPreviewUrlRef.current = null;
    }
    setVideoPreviewUrl(null);
    setSelectedFiles([]);
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
    if (!files || files.length === 0) {
      return;
    }

    const incoming = Array.from(files);
    const validFiles: File[] = [];
    const invalidFormat: string[] = [];
    const notStreamable: string[] = [];

    for (const file of incoming) {
      const fileName = file.name.toLowerCase();
      const fileType = file.type;

      // Validate file format
      if (!fileName.endsWith('.mp4') && fileType !== 'video/mp4') {
        invalidFormat.push(file.name);
        continue;
      }

      // Check if MP4 is streamable
      try {
        const streamable = await isStreamable(file);
        if (!streamable) {
          notStreamable.push(file.name);
          continue;
        }
      } catch (error) {
        console.error('Error checking streamability:', error);
      }

      validFiles.push(file);
    }

    // No usable files: preserve the single-file error semantics.
    if (validFiles.length === 0) {
      setFormatError(notStreamable.length > 0 ? t('OnlyStreamableMp4') : t('invalidVideoFormat'));
      setSelectedFiles([]);
      if (videoPreviewUrlRef.current) {
        URL.revokeObjectURL(videoPreviewUrlRef.current);
        videoPreviewUrlRef.current = null;
      }
      setVideoPreviewUrl(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      return;
    }

    // Some files were valid; surface a non-blocking notice for any skipped ones.
    const skipped = [...invalidFormat, ...notStreamable];
    if (skipped.length > 0) {
      setFormatError(`${t('skippedFiles')}: ${skipped.join(', ')}`);
    } else {
      setFormatError(null);
    }

    // Clean up previous preview URL if exists
    if (videoPreviewUrlRef.current) {
      URL.revokeObjectURL(videoPreviewUrlRef.current);
      videoPreviewUrlRef.current = null;
    }

    setSelectedFiles(validFiles);
    // Clear existing video selection when new files are selected
    setSelectedExistingVideo(null);
    // Preview the first selected file.
    const previewUrl = URL.createObjectURL(validFiles[0]);
    videoPreviewUrlRef.current = previewUrl;
    setVideoPreviewUrl(previewUrl);
  };

  // Handler for selecting an existing video
  const handleSelectExistingVideo = (video: Video) => {
    if (videoPreviewUrlRef.current) {
      URL.revokeObjectURL(videoPreviewUrlRef.current);
      videoPreviewUrlRef.current = null;
    }
    setSelectedFiles([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    setFormatError(null);
    setSelectedExistingVideo(video);
    const existingVideoUrl = buildSafeAssetVideoUrl(video);
    if (existingVideoUrl) {
      setVideoPreviewUrl(existingVideoUrl);
    } else {
      setVideoPreviewUrl(null);
    }
    if (video.tags && video.tags.length > 0) {
      setSelectedTags(video.tags);
    }
  };

  const uploadVideo = async (file: File, videoData: VideoUploadPayload) => {
    const formData = new FormData();

    formData.append('video', file);

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

  const triggerEmbeddings = async (videoId: string, tags?: string) => {
    const api = [videoUploadAPi, 'search-embeddings', videoId].join('/');
    const body = tags && tags.trim().length > 0 ? { tags } : undefined;
    try {
      const res = await axios.post<{ status: string; message: string }>(api, body);
      return res.data;
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const responseMessage = error.response?.data?.message;
        const status = error.response?.status;
        const timeoutHit =
          error.code === 'ECONNABORTED' ||
          status === 408 ||
          status === 504 ||
          /timeout/i.test(responseMessage || error.message || '');

        if (timeoutHit) {
          throw new Error(t('timeoutError'));
        }

        throw new Error(responseMessage || error.message);
      }
      throw error;
    }
  };

  const resolveErrorMessage = (error: unknown): string => {
    if (axios.isAxiosError(error)) {
      const responseMessage = error.response?.data?.message;
      const status = error.response?.status;
      const timeoutHit =
        error.code === 'ECONNABORTED' ||
        status === 408 ||
        status === 504 ||
        /timeout/i.test(responseMessage || error.message || '');

      if (timeoutHit) {
        return t('timeoutError');
      }
      if (responseMessage) {
        return responseMessage;
      }
      if (error.message) {
        return error.message;
      }
    } else if (error instanceof Error) {
      return error.message;
    }
    return t('videoUploadError');
  };

  // Submit one batch embeddings job for several already-uploaded videos.
  const submitBatchEmbeddings = async (
    videoIds: string[],
    tags?: string,
  ): Promise<BatchSubmitResponse> => {
    const api = [videoUploadAPi, 'search-embeddings-batch'].join('/');
    const body: { videoIds: string[]; tags?: string } = { videoIds };
    if (tags && tags.trim().length > 0) {
      body.tags = tags;
    }
    try {
      const res = await axios.post<BatchSubmitResponse>(api, body);
      return res.data;
    } catch (error) {
      throw new Error(resolveErrorMessage(error));
    }
  };

  // Poll a batch job until it reaches a terminal state, surfacing progress.
  const pollBatchJob = async (jobId: string): Promise<BatchJobStatus> => {
    const api = [videoUploadAPi, 'search-embeddings-jobs', jobId].join('/');
    const terminalStates = [
      'completed',
      'completed_with_errors',
      'failed',
      'cancelled',
    ];

    for (;;) {
      let status: BatchJobStatus;
      try {
        const res = await axios.get<BatchJobStatus>(api);
        status = res.data;
      } catch (error) {
        throw new Error(resolveErrorMessage(error));
      }

      const total = status.total || 0;
      const done = (status.completed || 0) + (status.failed || 0);
      setProgressText(`${t('CreatingEmbeddings')} (${done}/${total})`);

      if (terminalStates.includes(status.state)) {
        return status;
      }

      await new Promise((resolve) => setTimeout(resolve, BATCH_POLL_INTERVAL_MS));
    }
  };

  const buildVideoData = (): VideoUploadPayload => {
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

    return videoData;
  };

  const createEmbeddingForExistingVideo = async (videoData: VideoUploadPayload) => {
    try {
      setProcessing(true);
      setProgressText(t('CreatingEmbeddings'));

      const embeddingRes = await triggerEmbeddings(
        selectedExistingVideo!.videoId,
        videoData.tags,
      );

      if (embeddingRes.status === 'success') {
        setProgressText(t('allDone'));
        setProcessing(false);
        dispatch(videosLoad());
        dispatch(LoadTags());
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
      setProcessing(false);
      const errorMessage = resolveErrorMessage(error);
      setUploadErrorMessage(errorMessage);
      notify(errorMessage, NotificationSeverity.ERROR);
      setProgressText('');
    }
  };

  // Single file: keep the synchronous upload + embed path for immediate feedback.
  // Multiple files: upload every file, then submit ONE batch embeddings job and
  // poll it to completion (true batch, not sequential per-file embedding).
  const createEmbeddingsForFiles = async (videoData: VideoUploadPayload) => {
    const files = [...selectedFiles];

    if (files.length === 1) {
      await createEmbeddingForSingleFile(files[0], videoData);
      return;
    }

    await createEmbeddingsForFilesBatch(files, videoData);
  };

  const createEmbeddingForSingleFile = async (
    file: File,
    videoData: VideoUploadPayload,
  ) => {
    setUploadErrorMessage(null);
    try {
      setUploadProgress(0);
      setProcessing(false);
      setUploading(true);
      setProgressText(t('uploadingVideo'));

      const videoRes = await uploadVideo(file, videoData);
      dispatch(videosLoad());

      if (!videoRes.data.videoId) {
        throw new Error(t('serverError'));
      }

      setUploading(false);
      setProcessing(true);
      setProgressText(t('CreatingEmbeddings'));

      const embeddingRes = await triggerEmbeddings(videoRes.data.videoId, videoData.tags);
      if (embeddingRes.status !== 'success') {
        throw new Error(embeddingRes.message || t('unknownError'));
      }

      setUploading(false);
      setProcessing(false);
      setProgressText('');
      dispatch(videosLoad());
      dispatch(LoadTags());
      resetForm();
      notify(t('CreatingEmbeddings') + ' ' + t('success'), NotificationSeverity.SUCCESS);
      if (onClose) {
        onClose();
      }
    } catch (error: unknown) {
      console.error('Video upload/processing error:', error);
      setUploading(false);
      setProcessing(false);
      setProgressText('');
      const errorMessage = resolveErrorMessage(error);
      setUploadErrorMessage(errorMessage);
      notify(errorMessage, NotificationSeverity.ERROR);
    }
  };

  // Upload every selected file (isolating per-file upload failures), then embed
  // all successfully-uploaded videos through a single async batch job.
  const createEmbeddingsForFilesBatch = async (
    files: File[],
    videoData: VideoUploadPayload,
  ) => {
    const total = files.length;
    const uploadFailures: string[] = [];
    const uploadedVideoIds: string[] = [];

    setUploadErrorMessage(null);
    setUploading(true);
    setProcessing(false);

    // Phase 1: upload all files.
    for (let index = 0; index < total; index += 1) {
      const file = files[index];
      try {
        setUploadProgress(0);
        setProgressText(`${t('uploadingVideo')} (${index + 1}/${total})`);
        const videoRes = await uploadVideo(file, videoData);
        if (!videoRes.data.videoId) {
          throw new Error(t('serverError'));
        }
        uploadedVideoIds.push(videoRes.data.videoId);
      } catch (error: unknown) {
        console.error('Video upload error:', error);
        uploadFailures.push(`${file.name}: ${resolveErrorMessage(error)}`);
      }
    }

    dispatch(videosLoad());
    setUploading(false);

    if (uploadedVideoIds.length === 0) {
      setProgressText('');
      const errorMessage = `${t('videoUploadError')}: ${uploadFailures.join('; ')}`;
      setUploadErrorMessage(errorMessage);
      notify(errorMessage, NotificationSeverity.ERROR);
      return;
    }

    // Phase 2: one batch embeddings job for all uploaded videos.
    setProcessing(true);
    setProgressText(t('CreatingEmbeddings'));

    let jobStatus: BatchJobStatus;
    try {
      const submit = await submitBatchEmbeddings(uploadedVideoIds, videoData.tags);
      jobStatus = await pollBatchJob(submit.job_id);
    } catch (error: unknown) {
      console.error('Batch embeddings error:', error);
      setProcessing(false);
      setProgressText('');
      dispatch(videosLoad());
      const errorMessage = resolveErrorMessage(error);
      setUploadErrorMessage(errorMessage);
      notify(errorMessage, NotificationSeverity.ERROR);
      return;
    }

    setProcessing(false);
    setProgressText('');
    dispatch(videosLoad());
    dispatch(LoadTags());

    const embedFailed = jobStatus.failed || 0;
    const embedSucceeded = jobStatus.completed || 0;
    const allSucceeded = uploadFailures.length === 0 && embedFailed === 0;

    if (allSucceeded) {
      resetForm();
      notify(t('CreatingEmbeddings') + ' ' + t('success'), NotificationSeverity.SUCCESS);
      if (onClose) {
        onClose();
      }
      return;
    }

    const problems: string[] = [...uploadFailures];
    jobStatus.items
      .filter((item) => item.status === 'error')
      .forEach((item) => {
        problems.push(`${item.identifier}: ${item.message || t('unknownError')}`);
      });

    const errorMessage = `${embedSucceeded}/${total} ${t('success')}. ${t(
      'videoUploadError',
    )}: ${problems.join('; ')}`;
    setUploadErrorMessage(errorMessage);
    notify(errorMessage, NotificationSeverity.ERROR);
  };

  const triggerCreateEmbedding = async () => {
    const videoData = buildVideoData();

    if (selectedExistingVideo) {
      await createEmbeddingForExistingVideo(videoData);
      return;
    }

    await createEmbeddingsForFiles(videoData);
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
              {selectedExistingVideo && selectedFiles.length === 0 && (
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
                  {selectedFiles.length > 0 ? (
                    <>
                      {selectedFiles.length === 1 ? (
                        <h3 style={{ fontWeight: 600, fontSize: '1.2rem', marginBottom: '0.5rem' }}>
                          {selectedFiles[0].name}
                        </h3>
                      ) : (
                        <div style={{ marginBottom: '0.5rem' }}>
                          <h3 style={{ fontWeight: 600, fontSize: '1.2rem', marginBottom: '0.5rem' }}>
                            {selectedFiles.length} {t('videosSelected')}
                          </h3>
                          <ul
                            style={{
                              listStyle: 'none',
                              padding: 0,
                              margin: '0 auto',
                              maxHeight: '9rem',
                              overflowY: 'auto',
                              textAlign: 'left',
                              maxWidth: '420px',
                            }}
                          >
                            {selectedFiles.map((f, i) => (
                              <li
                                key={`${f.name}-${i}`}
                                title={f.name}
                                style={{
                                  whiteSpace: 'nowrap',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  fontSize: '0.95rem',
                                  padding: '0.15rem 0',
                                }}
                              >
                                {i + 1}. {f.name}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      <MainButton 
                        kind="tertiary" 
                        style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', margin: '0 auto' }}
                        onClick={(e: MouseEvent<HTMLButtonElement>) => {
                          e.stopPropagation();
                          if (videoPreviewUrlRef.current) {
                            URL.revokeObjectURL(videoPreviewUrlRef.current);
                            videoPreviewUrlRef.current = null;
                          }
                          setVideoPreviewUrl(null);
                          setSelectedFiles([]);
                          if (fileInputRef.current) {
                            fileInputRef.current.value = '';
                            // Open file picker after clearing
                            setTimeout(() => {
                              fileInputRef.current?.click();
                            }, 0);
                          }
                        }}
                      >
                        {selectedFiles.length > 1 ? t('changeVideos') : t('changeVideo')}
                      </MainButton>
                    </>
                  ) : (
                    <>
                      <div style={{ fontWeight: 500 }}>{t('uploadNew') || 'Upload New Video'}</div>
                      <div style={{ fontSize: '0.95rem', color: '#666', marginTop: '0.5rem' }}>
                        {t('dragAndDropMultiple')}
                      </div>
                    </>
                  )}
                  <input
                    type="file"
                    accept=".mp4"
                    multiple
                    style={{ display: 'none' }}
                    ref={fileInputRef}
                    onChange={e => handleFileSelect(e.target.files)}
                  />
                </DropArea>
              )}

              {/* Recent videos selector - only show when no file is selected and there are recent videos */}
              {selectedFiles.length === 0 && recentVideos.length > 0 && (
                <VideoSelectorContainer>
                  <VideoSelectorDivider>{t('orSelectExisting')}</VideoSelectorDivider>
                  <RecentVideosList>
                    {recentVideos.map((video) => {
                      const thumbnailUrl = buildSafeAssetVideoUrl(video);
                      return (
                        <RecentVideoItem
                          key={video.videoId}
                          selected={selectedExistingVideo?.videoId === video.videoId}
                          onClick={() => handleSelectExistingVideo(video)}
                        >
                          {thumbnailUrl && (
                            <VideoThumbnail
                              src={thumbnailUrl}
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
                      );
                    })}
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
                  labelText={createLabelWithTooltip(t('customVideoTags'), t('videoTagsinfo'))}
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
                {encodedSafeVideoPreviewUrl && (
                  <VideoPreviewContainer>
                    <StyledVideoPlayer controls>
                      <source src={encodedSafeVideoPreviewUrl} type="video/mp4" />
                      Your browser does not support the video tag.
                    </StyledVideoPlayer>
                  </VideoPreviewContainer>
                )}
                
                <div style={{ marginTop: encodedSafeVideoPreviewUrl ? '1rem' : '0' }}>
                  {selectedFiles.length > 1 ? (
                    <div>
                      <strong>{t('videoNameLabel')}:</strong> {selectedFiles.length}{' '}
                      {t('videosSelected')}
                      <ul
                        style={{
                          listStyle: 'none',
                          padding: 0,
                          margin: '0.5rem 0 0',
                          maxHeight: '9rem',
                          overflowY: 'auto',
                        }}
                      >
                        {selectedFiles.map((f, i) => (
                          <li
                            key={`review-${f.name}-${i}`}
                            title={f.name}
                            style={{
                              whiteSpace: 'nowrap',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              fontSize: '0.95rem',
                              padding: '0.15rem 0',
                            }}
                          >
                            {i + 1}. {f.name}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <div>
                      <strong>{t('videoNameLabel')}:</strong> {displayFileName || '-'}
                    </div>
                  )}
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
              disabled={selectedFiles.length === 0 && !selectedExistingVideo}
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
              disabled={uploading || (selectedFiles.length === 0 && !selectedExistingVideo)}
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
              disabled={uploading || (selectedFiles.length === 0 && !selectedExistingVideo)}
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