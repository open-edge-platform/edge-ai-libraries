// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Information } from '@carbon/icons-react';
import { useTranslation } from 'react-i18next';
import { useState, useRef, useEffect, Fragment, useCallback, useMemo } from 'react';
import styled from 'styled-components';
import {
  Accordion,
  AccordionItem,
  Button,
  Checkbox,
  ModalBody,
  ModalFooter,
  MultiSelect,
  NumberInput,
  ProgressBar,
  Select,
  SelectItem,
  TextInput,
  Toggletip,
  ToggletipButton,
  ToggletipContent,
} from '@carbon/react';

import { useAppSelector, useAppDispatch } from '../../redux/store';
import { SearchSelector } from '../../redux/search/searchSlice';
import { SummaryActions } from '../../redux/summary/summarySlice';
import { VideoChunkActions } from '../../redux/summary/videoChunkSlice';
import { VideoFramesAction } from '../../redux/summary/videoFrameSlice';
import { UIActions } from '../../redux/ui/ui.slice';
import { MuxFeatures } from '../../redux/ui/ui.model';
import { videosLoad } from '../../redux/video/videoSlice';
import { EVAMPipelines, SystemConfigWithMeta } from '../../redux/summary/summary';
import { SummaryPipelineDTO } from '../../redux/summary/summaryPipeline';
import { APP_URL } from '../../config';
import { PromptInput } from '../Prompts/PromptInput';
import axios from 'axios';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const toIdString = (value: unknown): string | undefined => {
  if (typeof value === 'string' && value.trim().length > 0) {
    return value;
  }
  if (typeof value === 'number') {
    return value.toString();
  }
  return undefined;
};

const walkPath = (source: unknown, path: string[]): unknown => {
  let current: unknown = source;
  for (const segment of path) {
    if (!isRecord(current)) {
      return undefined;
    }
    current = current[segment];
  }
  return current;
};

const gatherCandidates = (input: unknown): unknown[] => {
  const candidates: unknown[] = [];
  let current: unknown = input;
  let depth = 0;
  while (current !== undefined && depth < 4) {
    candidates.push(current);
    if (!isRecord(current) || !('data' in current)) {
      break;
    }
    current = (current as Record<string, unknown>).data;
    depth += 1;
  }
  return candidates;
};

const pickFirstId = (value: unknown, paths: string[][]): string | undefined => {
  for (const candidate of gatherCandidates(value)) {
    for (const path of paths) {
      const potential = toIdString(walkPath(candidate, path));
      if (potential) {
        return potential;
      }
    }
  }
  return undefined;
};

const CenteredContainer = styled.div` 
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  width: 100%;
  padding-bottom: 0 rem;  
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

const AccordionFieldGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding-top: 0.75rem;
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

const WarningBox = styled.p`
  background-color: #fff3cd;
  color: #856404;
  border-radius: 0px;
    padding: 1rem 1.5rem;
    margin-top: 1rem;
    font-size: 1rem;
    display: flex;
    align-items: center;
    gap: 0.7rem;
    box-shadow: 0 2px 8px rgba(255, 193, 7, 0.08);
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

export interface VideoSummarizeFlowProps {
  onClose?: () => void;
}

export default function VideoSummarizeFlow({ onClose }: VideoSummarizeFlowProps) {
  // API endpoints
  const summaryApi = `${APP_URL}/summary`;
  const videoUploadAPi = `${APP_URL}/videos`;
  const stateApi = `${APP_URL}/states`;

  // Helper to build summary pipeline DTO
  const getSummaryPipelineDTO = (videoId: string): SummaryPipelineDTO => {
    const title = summaryName || (selectedFile ? selectedFile.name.replace(/\.mp4$/i, '') : '');

    const fallbackEvamPipeline =
      (selectorRef?.current?.value as EVAMPipelines | undefined) ??
      systemConfig?.meta?.evamPipelines?.[0]?.value ??
      systemConfig?.evamPipeline ??
      EVAMPipelines.OBJECT_DETECTION;

    const pipelineData: SummaryPipelineDTO = {
      evam: { evamPipeline: fallbackEvamPipeline },
      sampling: {
        chunkDuration,
        samplingFrame: sampleFrame,
        frameOverlap,
        multiFrame: calculatedMultiFrame,
      },
      prompts: {
        framePrompt,
        summaryMapPrompt: mapPrompt,
        summaryReducePrompt: reducePrompt,
        summarySinglePrompt: singleReducePrompt,
      },
      videoId,
      title,
    };

    if (audio && systemConfig?.meta.defaultAudioModel) {
      pipelineData.audio = {
        audioModel: (audioModelRef?.current?.value as string | undefined) ?? systemConfig.meta.defaultAudioModel,
      };
    }

    return pipelineData;
  };
  // Upload video and trigger summary pipeline
  const triggerSummaryPipeline = async (videoId: string): Promise<unknown> => {
    const pipelineData = getSummaryPipelineDTO(videoId);
    try {
      const response = await axios.post(summaryApi, pipelineData, {
        headers: { 'Content-Type': 'application/json' },
      });
      return response.data;
    } catch (error) {
      console.error('Failed to trigger summary pipeline:', error);
      setProgressText(t('errorTriggeringPipeline', 'Unable to trigger summary pipeline.'));
      return null;
    }
  };

  const fetchUIState = async (stateId: string) => {
    return axios.get(`${stateApi}/${stateId}`);
  };

  const validateAndPrepareSummaryName = () => {
    let effectiveSummaryName = summaryName;
    if ((!effectiveSummaryName || effectiveSummaryName.trim() === '') && selectedFile) {
      effectiveSummaryName = selectedFile.name.replace(/\.mp4$/i, '');
      setSummaryName(effectiveSummaryName);
    }
    return effectiveSummaryName;
  };

  const prepareVideoUploadData = (effectiveSummaryName: string) => {
    const videoData: { tags?: string; name?: string } = {};
    const tags: string[] = [];
    if (videoTags) tags.push(...videoTags.split(',').map(tag => tag.trim()));
    if (selectedTags?.length > 0) tags.push(...selectedTags.map(tag => tag.trim()));
    if (tags.length > 0) videoData.tags = tags.join(',');
    videoData.name = effectiveSummaryName;
    return videoData;
  };

  const uploadVideo = async (videoData: { tags?: string; name?: string }) => {
    if (!selectedFile) {
      throw new Error('No video file selected.');
    }

    const formData = new FormData();
    formData.append('video', selectedFile);
    if (videoData.tags) formData.append('tags', videoData.tags);
    if (videoData.name) formData.append('name', videoData.name);

    return axios.post(videoUploadAPi, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (ev) => setUploadProgress((ev.progress ?? 0) * 100),
    });
  };

  const extractVideoId = (uploadResponse: unknown) =>
    pickFirstId(uploadResponse, [
      ['videoId'],
      ['video_id'],
      ['id'],
      ['video', 'videoId'],
      ['video', 'video_id'],
      ['video', 'id'],
      ['payload', 'videoId'],
      ['payload', 'video_id'],
      ['payload', 'id'],
      ['data', 'videoId'],
      ['data', 'video_id'],
      ['data', 'id'],
    ]);

  const resolveSummaryPipelineId = (pipelineRes: unknown) =>
    pickFirstId(pipelineRes, [
      ['summaryPipelineId'],
      ['summary_pipeline_id'],
      ['stateId'],
      ['state_id'],
      ['pipelineId'],
      ['pipeline_id'],
      ['id'],
      ['payload', 'summaryPipelineId'],
      ['payload', 'summary_pipeline_id'],
      ['payload', 'stateId'],
      ['payload', 'state_id'],
      ['payload', 'id'],
      ['data', 'summaryPipelineId'],
      ['data', 'summary_pipeline_id'],
      ['data', 'stateId'],
      ['data', 'state_id'],
      ['data', 'pipelineId'],
      ['data', 'pipeline_id'],
      ['data', 'id'],
    ]);

  const handleSummaryPipelineResult = async (pipelineRes: unknown) => {
    const summaryPipelineId = resolveSummaryPipelineId(pipelineRes);
    if (!summaryPipelineId) {
      setProgressText(t('errorFetchingSummary', 'Unable to start summary – missing pipeline identifier.'));
      console.error('Missing summary pipeline identifier in response:', pipelineRes);
      return;
    }

    setProgressText(t('Fetching summary state...'));
    const uiState = await fetchUIState(summaryPipelineId);
    
    if (uiState) {
      dispatch(SummaryActions.addSummary(uiState.data));
      dispatch(SummaryActions.selectSummary(summaryPipelineId));
      dispatch(VideoChunkActions.setSelectedSummary(summaryPipelineId));
      dispatch(VideoFramesAction.selectSummary(summaryPipelineId));
      dispatch(UIActions.setMux(MuxFeatures.SUMMARY));
      setProgressText(t('allDone'));
      void resetForm();
      if (onClose) onClose();
    }
  };

  const triggerSummary = async () => {
    try {
      const effectiveSummaryName = validateAndPrepareSummaryName();
      if (!effectiveSummaryName || effectiveSummaryName.trim() === '') {
        setProgressText('Summary name (title) is required.');
        return;
      }

      setUploading(true);
      setProgressText(t('uploadingVideo'));

      const videoData = prepareVideoUploadData(effectiveSummaryName);
      const videoRes = await uploadVideo(videoData);

      dispatch(videosLoad());
      setUploading(false);
      setProcessing(true);

      const uploadedVideoId = extractVideoId(videoRes);

      if (!uploadedVideoId) {
        setProgressText(t('errorMissingVideoId', 'Upload succeeded but no video identifier was returned.'));
        console.error('Unable to resolve video identifier from upload response:', videoRes?.data ?? videoRes);
        return;
      }

      setProgressText(t('TriggeringPipeline'));
      const pipelineRes = await triggerSummaryPipeline(uploadedVideoId);
      await handleSummaryPipelineResult(pipelineRes);
    } catch (error: unknown) {
      let errorMessage = 'Unknown error';
      if (axios.isAxiosError(error)) {
        const responseData = error.response?.data;
        if (
          responseData &&
          typeof responseData === 'object' &&
          'message' in responseData &&
          typeof (responseData as { message?: unknown }).message === 'string'
        ) {
          errorMessage = (responseData as { message: string }).message;
        } else if (error.message) {
          errorMessage = error.message;
        }
      } else if (error instanceof Error) {
        errorMessage = error.message || errorMessage;
      }

      setProgressText(`Error: ${errorMessage}`);
      console.error('Trigger summary error:', error);
    } finally {
      setUploading(false);
      setProcessing(false);
    }
  };
  const { t } = useTranslation();
  const dispatch = useAppDispatch();
  const { suggestedTags } = useAppSelector(SearchSelector);

  // UI State
  const [step, setStep] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [processing, setProcessing] = useState(false);
  const [progressText, setProgressText] = useState('');

  // Video & Summary State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [summaryName, setSummaryName] = useState('');
  const [videoTags, SetVideoTags] = useState<string | null>('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagsMenuOpen, setTagsMenuOpen] = useState(false);
  const [videoPreviewUrl, setVideoPreviewUrl] = useState<string | null>(null);

  // Configuration State
  const [chunkDuration, setChunkDuration] = useState(8);
  const [sampleFrame, setSampleFrame] = useState(8);
  const [frameOverlap, setFrameOverlap] = useState(4);
  const [audio, setAudio] = useState(true);
  const [systemConfig, setSystemConfig] = useState<SystemConfigWithMeta>();

  // Prompt State
  const [framePrompt, setFramePrompt] = useState('');
  const [mapPrompt, setMapPrompt] = useState('');
  const [reducePrompt, setReducePrompt] = useState('');
  const [singleReducePrompt, setSingleReducePrompt] = useState('');

  // Accordion State - track which items are open
  const [accordionOpen, setAccordionOpen] = useState({
    ingestion: false,
    audio: false,
    prompts: false
  });

  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoLabelRef = useRef<HTMLInputElement>(null);
  const selectorRef = useRef<HTMLSelectElement>(null);
  const audioModelRef = useRef<HTMLSelectElement>(null);
  const videoPreviewUrlRef = useRef<string | null>(null);
  const shouldKeepTagsMenuOpenRef = useRef(false);

  const calculatedMultiFrame = useMemo(
    () => sampleFrame + frameOverlap,
    [sampleFrame, frameOverlap]
  );

  useEffect(() => {
    if (systemConfig) {
      setFramePrompt(systemConfig.framePrompt);
      setMapPrompt(systemConfig.summaryMapPrompt);
      setReducePrompt(systemConfig.summaryReducePrompt);
      setSingleReducePrompt(systemConfig.summarySinglePrompt);
    }
  }, [systemConfig]);

  useEffect(() => {
    if (step !== 1) {
      setTagsMenuOpen(false);
      shouldKeepTagsMenuOpenRef.current = false;
    }
  }, [step]);

  const resetForm = useCallback(async () => {
    // Clean up video preview URL first
    if (videoPreviewUrlRef.current) {
      URL.revokeObjectURL(videoPreviewUrlRef.current);
      videoPreviewUrlRef.current = null;
    }
    setVideoPreviewUrl(null);
    setSelectedFile(null);
    setSummaryName('');
    setSampleFrame(8);
    setChunkDuration(8);
    setFrameOverlap(4);
    setProgressText('');
    setUploadProgress(0);
    setUploading(false);
    setProcessing(false);
    setStep(0);
  SetVideoTags('');
  setSelectedTags([]);
  setTagsMenuOpen(false);
  shouldKeepTagsMenuOpenRef.current = false;
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (videoLabelRef.current) videoLabelRef.current.value = '';
    
    try {
      const res = await axios.get<SystemConfigWithMeta>(`${APP_URL}/app/config`);
      if (res.data) setSystemConfig(res.data);
    } catch (error) {
      console.error('Failed to load system config:', error);
    }
  }, []); // Empty dependency array - stable reference

  useEffect(() => {
    void resetForm();
    dispatch(UIActions.closePrompt());
  }, [resetForm, dispatch]);

  // Cleanup video preview URL on unmount
  useEffect(() => {
    return () => {
      if (videoPreviewUrlRef.current) {
        URL.revokeObjectURL(videoPreviewUrlRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (selectedFile) {
      const fileName = selectedFile.name.replace(/\.mp4$/i, '');
      setSummaryName(fileName);
      // Also update the ref if it exists
      if (videoLabelRef.current) {
        videoLabelRef.current.value = fileName;
      }
    }
  }, [selectedFile]);

  const frameOverlapChange = (val: number) => {
    const numericValue = Number.isFinite(val) ? val : 0;
    const nonNegativeValue = Math.max(0, numericValue);
    setFrameOverlap(nonNegativeValue);
  };

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

  const createLabelWithTooltip = (label: string, tooltipContent: string) => (
    <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      {label}
      <Toggletip autoAlign>
        <ToggletipButton>
          <Information />
        </ToggletipButton>
        <ToggletipContent>{tooltipContent}</ToggletipContent>
      </Toggletip>
    </span>
  );


  const timelineSteps = useMemo(
    () => [t('SelectVideo'), t('Set Parameter'), t('ReviewAndCreate')],
    [t]
  );

  return (
    <>
      <ModalBody>
        <CenteredContainer>
          <TimelineContainer>
            {timelineSteps.map((label, idx) => {
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
                  {idx < timelineSteps.length - 1 && (
                    <TimelineConnector completed={step > idx} />
                  )}
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
                  <h3 style={{ fontWeight: 600, fontSize: '1.2rem', marginBottom: '0.5rem' }}>{selectedFile.name}</h3>
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
                      setSummaryName('');
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
                  <div style={{ fontSize: '0.95rem', color: '#666', marginTop: '0.5rem' }}>or drag and drop here</div>
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
                {/* Video Name and Tags */}
                <TextInput
                  ref={videoLabelRef}
                  onChange={ev => setSummaryName(ev.currentTarget.value)}
                  labelText={createLabelWithTooltip(t('summaryTitle'), t('videoSummaryinfo'))}
                  id='summaryname'
                  style={{ flex: 1 }}
                  value={summaryName || ''}
                />
                {suggestedTags && suggestedTags.length > 0 && (
                  <MultiSelect
                    items={suggestedTags}
                    itemToString={item => (item ? item : '')}
                    selectedItems={selectedTags}
                    onChange={data => {
                      if (data.selectedItems) {
                        setSelectedTags(data.selectedItems);
                      }
                      shouldKeepTagsMenuOpenRef.current = true;
                      setTagsMenuOpen(true);
                    }}
                    id='availabel-tags-selector'
                    label={t('availableVideoTags')}
                    onMenuChange={open => {
                      if (!open && shouldKeepTagsMenuOpenRef.current) {
                        shouldKeepTagsMenuOpenRef.current = false;
                        setTagsMenuOpen(true);
                        return;
                      }
                      shouldKeepTagsMenuOpenRef.current = false;
                      setTagsMenuOpen(open);
                    }}
                    open={tagsMenuOpen}
                    sortItems={() => suggestedTags}
                  />
                )}
                <TextInput
                  labelText={createLabelWithTooltip(t('customVideoTags'), t('videoTagsinfo'))}
                  onChange={ev => SetVideoTags(ev.currentTarget.value)}
                  id='videoTags'
                  value={videoTags || ''}
                />
                <NumberInput
                  step={1}
                  min={2}
                  value={chunkDuration}
                  onChange={(_evt, { value }) => setChunkDuration(Number(value))}
                  label={createLabelWithTooltip(t('ChunkDurationLabel'), t('ChunkDurationInfo'))}
                  id='chunkDuration'
                />
                <NumberInput
                  step={1}
                  min={2}
                  value={sampleFrame}
                  onChange={(_evt, { value }) => setSampleFrame(Number(value))}
                  label={createLabelWithTooltip(t('FramePerChunkLabel'), t('FramePerChunkInfo'))}
                  id='sampleFrame'
                />
                {systemConfig && (
                  <Accordion align="start">
                    <AccordionItem 
                      title={t('IngestionSettings')}
                      open={accordionOpen.ingestion}
                      onHeadingClick={() => setAccordionOpen(prev => ({ ...prev, ingestion: !prev.ingestion }))}
                    >
                      <AccordionFieldGroup>
                        <NumberInput
                          id='overrideMultiFrame'
                          value={frameOverlap}
                          min={0}
                          max={systemConfig.multiFrame}
                          onChange={(_evt, { value }) => frameOverlapChange(Number(value))}
                          label={createLabelWithTooltip(t('FramesOverlap'), t('FramesOverlapInfo'))}
                        />
                        <TextInput
                          id='overrideOverlap'
                          type='number'
                          value={calculatedMultiFrame.toString()}
                          readOnly
                          labelText={createLabelWithTooltip(t('MultiFrame'), t('MultiFrameInfo'))}
                        />
                        {systemConfig.meta.evamPipelines && (
                          <Select 
                            id='evam-pipeline-select' 
                            labelText={createLabelWithTooltip(t('Chunking Pipeline'), t('ChunkingPipelineInfo'))} 
                            ref={selectorRef}
                          >
                            {systemConfig.meta.evamPipelines.map((option: { name: string; value: string }) => (
                              <SelectItem key={option.value} text={option.name} value={option.value} />
                            ))}
                          </Select>
                        )}
                      </AccordionFieldGroup>
                    </AccordionItem>
                    {systemConfig.meta.defaultAudioModel && (
                      <AccordionItem 
                        title={t('AudioSettings')}
                        open={accordionOpen.audio}
                        onHeadingClick={() => setAccordionOpen(prev => ({ ...prev, audio: !prev.audio }))}
                      >
                        <Checkbox
                          id='audiocheckBox'
                          labelText={t('UseAudio')}
                          defaultChecked={true}
                          onChange={(_, { checked }) => setAudio(checked)}
                        />
                        {audio && (
                          <Select 
                            id='audioModelsSelector' 
                            labelText={createLabelWithTooltip(t('AudioModels'), t('AudioModelsInfo'))} 
                            ref={audioModelRef}
                          >
                            {systemConfig.meta.audioModels.map((option: { display_name: string; model_id: string }) => (
                              <SelectItem key={option.model_id} text={option.display_name} value={option.model_id} />
                            ))}
                          </Select>
                        )}
                      </AccordionItem>
                    )}
                    <AccordionItem 
                      title={t('PromptSettings')}
                      open={accordionOpen.prompts}
                      onHeadingClick={() => setAccordionOpen(prev => ({ ...prev, prompts: !prev.prompts }))}
                    >
                      <PromptInput
                        label={t('FramePrompt')}
                        infoLabel={t('FramePromptInfo')}
                        defaultVal={systemConfig.framePrompt}
                        description={t('FramePromptDescription')}
                        onChange={newPrompt => setFramePrompt(newPrompt)}
                        reset={() => systemConfig && setFramePrompt(systemConfig.framePrompt)}
                        opener='FRAME_PROMPT'
                        prompt={framePrompt}
                        editHeading={t('FramePromptEditing')}
                      />
                      <PromptInput
                        label={t('SummaryPrompt')}
                        infoLabel={t('SummaryPromptInfo')}
                        defaultVal={systemConfig.summaryMapPrompt}
                        description={t('SummaryPromptDescription')}
                        onChange={newPrompt => setMapPrompt(newPrompt)}
                        reset={() => systemConfig && setMapPrompt(systemConfig.summaryMapPrompt)}
                        opener='MAP_PROMPT'
                        prompt={mapPrompt}
                        editHeading={t('SummaryPromptEditing')}
                      />
                      <PromptInput
                        label={t('SummaryReducePrompt')}
                        infoLabel={t('SummaryReducePromptInfo')}
                        defaultVal={systemConfig.summaryReducePrompt}
                        description={t('SummaryReducePromptDescription')}
                        onChange={newPrompt => setReducePrompt(newPrompt)}
                        reset={() => systemConfig && setReducePrompt(systemConfig.summaryReducePrompt)}
                        editHeading={t('SummaryReducePromptEditing')}
                        opener='REDUCE_PROMPT'
                        prompt={reducePrompt}
                      />
                      <PromptInput
                        label={t('SummarySinglePrompt')}
                        infoLabel={t('SummarySinglePromptInfo')}
                        defaultVal={systemConfig.summarySinglePrompt}
                        description={t('SummarySinglePromptDescription')}
                        onChange={newPrompt => setSingleReducePrompt(newPrompt)}
                        reset={() => systemConfig && setSingleReducePrompt(systemConfig.summarySinglePrompt)}
                        editHeading={t('SummarySinglePromptEditing')}
                        opener='SINGLE_PROMPT'
                        prompt={singleReducePrompt}
                      />
                    </AccordionItem>
                  </Accordion>
                )}
                <p style={{ marginTop: '1rem' }}>
                  {t('sampleRate', { frames: sampleFrame, interval: chunkDuration })}
                </p>
                {systemConfig && frameOverlap + sampleFrame > systemConfig.multiFrame && (
                  <WarningBox>
                    {t('frameOverlapWarning', {
                      frames: frameOverlap + sampleFrame,
                      maxFrames: systemConfig.multiFrame,
                    })}
                  </WarningBox>
                )}
              </SettingsPanel>
            </>
          )}
          {step === 2 && (
            <>
              <div style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                minHeight: '300px',
                textAlign: 'center',
                gap: '1.5rem',
                width: '100%'
              }}>
                <div style={{
                  background: '#f4f4f4',
                  border: '1px solid #e0e0e0',
                  borderRadius: '8px',
                  padding: '1.5rem 2rem',
                  textAlign: 'left',
                  maxWidth: '600px',
                  width: '100%'
                }}>
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
                    <div><strong>{t('summaryTitle')}:</strong> {summaryName}</div>
                    {videoTags && videoTags.trim().length > 0 && (
                      <div><strong>{t('customVideoTags')}:</strong> {videoTags}</div>
                    )}
                    <div><strong>{t('ChunkDurationLabel')}:</strong> {chunkDuration}</div>
                    <div><strong>{t('FramePerChunkLabel')}:</strong> {sampleFrame}</div>
                    {systemConfig && (
                      <>
                        <div style={{ marginTop: '1rem', fontWeight: 600 }}>{t('IngestionSettings')}</div>
                        <div><strong>{t('FramesOverlap')}:</strong> {frameOverlap}</div>
                        <div><strong>{t('MultiFrame')}:</strong> {calculatedMultiFrame}</div>
                        <div><strong>{t('Chunking Pipeline')}:</strong> {selectorRef?.current?.value ?? ''}</div>
                        {systemConfig.meta.defaultAudioModel && (
                          <>
                            <div style={{ marginTop: '1rem', fontWeight: 600 }}>{t('AudioSettings')}</div>
                            <div><strong>{t('UseAudio')}:</strong> {audio ? t('yes') : t('no')}</div>
                            <div><strong>{t('AudioModels')}:</strong> {audioModelRef?.current?.value ?? systemConfig.meta.defaultAudioModel}</div>
                          </>
                        )}
                        {(framePrompt !== systemConfig.framePrompt || 
                          mapPrompt !== systemConfig.summaryMapPrompt || 
                          reducePrompt !== systemConfig.summaryReducePrompt || 
                          singleReducePrompt !== systemConfig.summarySinglePrompt) && (
                          <>
                            <div style={{ marginTop: '1rem', fontWeight: 600 }}>{t('PromptSettings')} ({t('Modified', 'Modified')})</div>
                            {framePrompt !== systemConfig.framePrompt && (
                              <div><strong>{t('FramePrompt')}:</strong> {framePrompt}</div>
                            )}
                            {mapPrompt !== systemConfig.summaryMapPrompt && (
                              <div><strong>{t('SummaryPrompt')}:</strong> {mapPrompt}</div>
                            )}
                            {reducePrompt !== systemConfig.summaryReducePrompt && (
                              <div><strong>{t('SummaryReducePrompt')}:</strong> {reducePrompt}</div>
                            )}
                            {singleReducePrompt !== systemConfig.summarySinglePrompt && (
                              <div><strong>{t('SummarySinglePrompt')}:</strong> {singleReducePrompt}</div>
                            )}
                          </>
                        )}
                      </>
                    )}
                  </div>
                </div>
                {uploading && (
                  <ProgressBar value={uploadProgress} helperText={uploadProgress.toFixed(2) + '%'} label={progressText} />
                )}
                {processing && <ProgressBar label={progressText} />}
              </div>
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
                void resetForm();
                if (onClose) {
                  onClose();
                }
              }}
            >
              {t('cancel')}
            </Button>
            <Button kind="primary" disabled={!selectedFile} onClick={() => setStep(1)}>
              Next
            </Button>
          </>
        ) : step === 1 ? (
          <>
            <Button kind="secondary" onClick={() => setStep(0)}>
              Back
            </Button>
            <Button kind="primary" onClick={() => setStep(2)}>
              Next
            </Button>
          </>
        ) : (
          <>
            <Button kind="secondary" disabled={uploading || processing} onClick={() => setStep(1)}>
              Back
            </Button>
            <Button kind="primary" disabled={uploading || !selectedFile} onClick={triggerSummary}>
              {uploading ? t('uploadingVideoState') : t('CreateSummary')}
            </Button>
          </>
        )}
      </StyledModalFooter>
    </>
  );
}
