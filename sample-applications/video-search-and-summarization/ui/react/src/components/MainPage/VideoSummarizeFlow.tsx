// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Information } from '@carbon/icons-react';
import { useTranslation } from 'react-i18next';
import { useState, useRef, useEffect } from 'react';
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
import { SystemConfigWithMeta } from '../../redux/summary/summary';
import { APP_URL } from '../../config';
import { PromptInput } from '../Prompts/PromptInput';
import axios from 'axios';

const CenteredContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  width: 100%;
  max-height: calc(80vh - 120px);
  overflow: hidden;
`;

const DropArea = styled.div<{ dragging: boolean }>`
  border: 2.5px dashed #0072c3;
    border-radius: 0px;
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
  border-radius: 0px;
  background: ${({ active }) => (active ? 'var(--color-info)' : '#e0e0e0')};
  color: ${({ active }) => (active ? 'var(--color-white)' : '#333')};
  font-weight: ${({ active }) => (active ? 'bold' : 'normal')};
  font-size: 1.1rem;
  box-shadow: ${({ active }) => (active ? '0 2px 12px rgba(0,114,195,0.10)' : 'none')};
  transition: background 0.2s, color 0.2s;
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
  const getSummaryPipelineDTO = (videoId: string) => {
    const title = summaryName || (selectedFile ? selectedFile.name.replace(/\.mp4$/i, '') : '');
    
    const pipelineData = {
      evam: { evamPipeline: selectorRef?.current?.value ?? '' },
      sampling: {
        chunkDuration,
        samplingFrame: sampleFrame,
        frameOverlap,
        multiFrame: systemConfig ? Math.min(multiFrame, systemConfig.multiFrame) : multiFrame,
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
      Object.assign(pipelineData, {
        audio: { audioModel: audioModelRef?.current?.value ?? systemConfig.meta.defaultAudioModel }
      });
    }

    return pipelineData;
  };
  // Upload video and trigger summary pipeline
  const triggerSummaryPipeline = async (videoId: string) => {
    const pipelineData = getSummaryPipelineDTO(videoId);
    const response = await axios.post(summaryApi, pipelineData, {
      headers: { 'Content-Type': 'application/json' },
    });
    return response.data;
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

  const handleSummaryPipelineResult = async (pipelineRes: any) => {
    if (!pipelineRes?.summaryPipelineId) return;

    setProgressText(t('Fetching summary state...'));
    const uiState = await fetchUIState(pipelineRes.summaryPipelineId);
    
    if (uiState) {
      dispatch(SummaryActions.addSummary(uiState.data));
      dispatch(SummaryActions.selectSummary(pipelineRes.summaryPipelineId));
      dispatch(VideoChunkActions.setSelectedSummary(pipelineRes.summaryPipelineId));
      dispatch(VideoFramesAction.selectSummary(pipelineRes.summaryPipelineId));
      dispatch(UIActions.setMux(MuxFeatures.SUMMARY));
      setProgressText(t('allDone'));
      resetForm();
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

      if (videoRes.data?.videoId) {
        setProgressText(t('TriggeringPipeline'));
        const pipelineRes = await triggerSummaryPipeline(videoRes.data.videoId);
        await handleSummaryPipelineResult(pipelineRes);
      }
    } catch (error) {
      const e = error as any;
      const errorMessage = e?.response?.data?.message || e?.message || 'Unknown error';
      setProgressText(`Error: ${errorMessage}`);
      console.error('Trigger summary error:', error);
    } finally {
      setUploading(false);
      setProcessing(false);
    }
  };
  // Styled Components
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
    max-height: 50vh;
  `;

  const StyledModalFooter = styled(ModalFooter)`
    padding: 1.5rem 0 0 0 !important;
    margin: 0 -1rem -1rem -1rem !important;
    z-index: 10 !important;
    position: relative !important;
  `;
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

  // Configuration State
  const [chunkDuration, setChunkDuration] = useState(8);
  const [sampleFrame, setSampleFrame] = useState(8);
  const [frameOverlap, setFrameOverlap] = useState(4);
  const [multiFrame, setMultiFrame] = useState(12);
  const [audio, setAudio] = useState(true);
  const [systemConfig, setSystemConfig] = useState<SystemConfigWithMeta>();

  // Prompt State
  const [framePrompt, setFramePrompt] = useState('');
  const [mapPrompt, setMapPrompt] = useState('');
  const [reducePrompt, setReducePrompt] = useState('');
  const [singleReducePrompt, setSingleReducePrompt] = useState('');

  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoLabelRef = useRef<HTMLInputElement>(null);
  const selectorRef = useRef<HTMLSelectElement>(null);
  const audioModelRef = useRef<HTMLSelectElement>(null);

  useEffect(() => {
    if (systemConfig) {
      updateMultiFrame(sampleFrame, frameOverlap);
      setFramePrompt(systemConfig.framePrompt);
      setMapPrompt(systemConfig.summaryMapPrompt);
      setReducePrompt(systemConfig.summaryReducePrompt);
      setSingleReducePrompt(systemConfig.summarySinglePrompt);
    }
  }, [sampleFrame, frameOverlap, systemConfig]);

  const resetForm = async () => {
    setSelectedFile(null);
    setSummaryName('');
    setSampleFrame(8);
    setChunkDuration(8);
    setProgressText('');
    setUploadProgress(0);
    setUploading(false);
    setProcessing(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (videoLabelRef.current) videoLabelRef.current.value = '';
    
    try {
      const res = await axios.get<SystemConfigWithMeta>(`${APP_URL}/app/config`);
      if (res.data) setSystemConfig(res.data);
    } catch (error) {
      console.error('Failed to load system config:', error);
    }
  };

  useEffect(() => {
    resetForm();
    dispatch(UIActions.closePrompt());
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
    setFrameOverlap(val);
    updateMultiFrame(sampleFrame, val);
  };

  const updateMultiFrame = (sampleFrames: number, overlap: number) => {
    if (systemConfig) {
      const calculatedMultiFrame = Math.min(sampleFrames + overlap, systemConfig.multiFrame);
      setMultiFrame(calculatedMultiFrame);
    }
  };

  const handleFileSelect = (files: FileList | null) => {
    if (files && files.length > 0) {
      setSelectedFile(files[0]);
    }
  };

  const createLabelWithTooltip = (label: string, tooltipContent: string) => (
    <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      {label}
      <Toggletip>
        <ToggletipButton>
          <Information />
        </ToggletipButton>
        <ToggletipContent>{tooltipContent}</ToggletipContent>
      </Toggletip>
    </span>
  );


  return (
    <>
      <ModalBody>
        <CenteredContainer>
          <Stepper>
            <Step active={step === 0}>{t('SelectVideo')}</Step>
            <Step active={step === 1}>{t('Set Parameter')}</Step>
            <Step active={step === 2}>{t('CreateSummary')}</Step>
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
                  <h3 style={{ fontWeight: 600, fontSize: '1.2rem', marginBottom: '0.5rem' }}>{selectedFile.name}</h3>
                  <MainButton kind="tertiary" onClick={() => {
                    setSelectedFile(null);
                    setSummaryName('');
                  }}>{t('changeVideo')}</MainButton>
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
                    onChange={data => {
                      if (data.selectedItems) {
                        setSelectedTags(data.selectedItems);
                      }
                    }}
                    id='availabel-tags-selector'
                    label={t('availableVideoTags')}
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
                  <Accordion>
                    <AccordionItem title={t('IngestionSettings')}>
                      <NumberInput
                        id='overrideMultiFrame'
                        value={frameOverlap}
                        min={0}
                        max={systemConfig.multiFrame}
                        onChange={(_evt, { value }) => frameOverlapChange(Number(value))}
                        label={createLabelWithTooltip(t('FramesOverlap'), t('FramesOverlapInfo'))}
                      />
                      <NumberInput
                        id='overrideOverlap'
                        value={multiFrame}
                        max={systemConfig.multiFrame}
                        readOnly={true}
                        label={createLabelWithTooltip(t('MultiFrame'), t('MultiFrameInfo'))}
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
                    </AccordionItem>
                    {systemConfig.meta.defaultAudioModel && (
                      <AccordionItem title={t('AudioSettings')}>
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
                    <AccordionItem title={t('PromptSettings')}>
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
                gap: '2rem',
                width: '100%'
              }}>
                <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: '#333', marginBottom: '1rem' }}>
                  {t('ReadyToCreateSummary')}
                </h2>
                <div style={{
                  background: '#f4f4f4',
                  border: '1px solid #e0e0e0',
                  borderRadius: '8px',
                  padding: '1.5rem 2rem',
                  marginBottom: '1.5rem',
                  textAlign: 'left',
                  maxWidth: '600px',
                  width: '100%'
                }}>
                  <h3 style={{ fontWeight: 600, marginBottom: '1rem' }}>{t('Preview')}</h3>
                  <div><strong>{t('summaryTitle')}:</strong> {summaryName}</div>
                  <div><strong>{t('customVideoTags')}:</strong> {videoTags}</div>
                  <div><strong>{t('availableVideoTags')}:</strong> {selectedTags && selectedTags.length > 0 ? selectedTags.join(', ') : '-'}</div>
                  <div><strong>{t('ChunkDurationLabel')}:</strong> {chunkDuration}</div>
                  <div><strong>{t('FramePerChunkLabel')}:</strong> {sampleFrame}</div>
                  {systemConfig && (
                    <>
                      <div style={{ marginTop: '1rem', fontWeight: 600 }}>{t('IngestionSettings')}</div>
                      <div><strong>{t('FramesOverlap')}:</strong> {frameOverlap}</div>
                      <div><strong>{t('MultiFrame')}:</strong> {multiFrame}</div>
                      <div><strong>{t('Chunking Pipeline')}:</strong> {selectorRef?.current?.value ?? ''}</div>
                      {systemConfig.meta.defaultAudioModel && (
                        <>
                          <div style={{ marginTop: '1rem', fontWeight: 600 }}>{t('AudioSettings')}</div>
                          <div><strong>{t('UseAudio')}:</strong> {audio ? t('yes') : t('no')}</div>
                          <div><strong>{t('AudioModels')}:</strong> {audioModelRef?.current?.value ?? systemConfig.meta.defaultAudioModel}</div>
                        </>
                      )}
                    </>
                  )}
                </div>
                <p style={{ fontSize: '1rem', color: '#666', maxWidth: '400px', lineHeight: '1.5' }}>
                  {t('CreateSummaryDescription')}
                </p>
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
