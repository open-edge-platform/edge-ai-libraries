// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import {
  Accordion,
  AccordionItem,
  Button,
  Checkbox,
  MultiSelect,
  NumberInput,
  ProgressBar,
  Select,
  SelectItem,
  TextInput,
} from '@carbon/react';
import axios, { AxiosProgressEvent, AxiosResponse } from 'axios';
import { FC, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import { EVAMPipelines, SystemConfigWithMeta, UIState } from '../../redux/summary/summary';
import { SummaryActions } from '../../redux/summary/summarySlice';
import { APP_URL } from '../../config';
import { VideoChunkActions } from '../../redux/summary/videoChunkSlice';
import { VideoFramesAction } from '../../redux/summary/videoFrameSlice';
import { PromptInput } from '../Prompts/PromptInput';
import { UIActions } from '../../redux/ui/ui.slice';
import { NotificationSeverity, notify } from '../Notification/notify';
import { VideoDTO, VideoRO } from '../../redux/video/video';
import { SummaryPipelineDTO, SummaryPipelinRO } from '../../redux/summary/summaryPipeline';
import { videosLoad } from '../../redux/video/videoSlice';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { MuxFeatures } from '../../redux/ui/ui.model';
import { SearchSelector } from '../../redux/search/searchSlice';

export interface VideoUploadProps {
  closeDrawer: () => void;
  isOpen: boolean;
}

export interface VideoUploadDTO {
  videoName: string;
  chunkDuration: number;
  samplingFrame: number;
  samplingInterval: number;
  videoFile: any;
}

const VideoFormContainer = styled.div`
  display: flex;
  flex-flow: column nowrap;
  align-items: flex-start;
  justify-content: flex-start;
  padding: 1rem;
  overflow-y: auto;

  & > * {
    width: 100%;
  }
  .selected-file-name {
    word-wrap: break-word;
  }
`;

const FullWidthButton = styled(Button)`
  min-width: 100%;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  justify-content: center;
`;

const TextInputStyled = styled(TextInput)`
  margin-top: 1rem;
`;

const NumberInputStyled = styled(NumberInput)`
  margin-top: 1rem;
`;

const SelectInputStyled = styled(Select)`
  margin-top: 1rem;
`;

const HiddenFileInput = styled.input`
  display: none;
`;

const MessageBox = styled.p`
  display: flex;
  flex-flow: row nowrap;
  align-items: center;
  justify-content: flex-start;
  padding: 1rem;
`;

const WarningContainer = styled.p`
  display: flex;
  flex-flow: row nowrap;
  align-items: center;
  justify-content: flex-start;
  padding: 1rem;
  background-color: var(--color-warning);
`;

const StyledAcc = styled(Accordion)`
  margin-top: 1rem;
`;

export const VideoUpload: FC<VideoUploadProps> = ({ closeDrawer, isOpen }) => {
  const { t } = useTranslation();

  const minDuration: number = 2;
  const minFrames: number = 2;
  const defaultSampleFrames: number = 8;
  const defaultChunkDuration: number = 8;
  const defaultOverlap: number = 4;

  const dispatch = useAppDispatch();
  const summaryApi = `${APP_URL}/summary`;
  const videoUploadAPi = `${APP_URL}/videos`;
  const stateApi = `${APP_URL}/states`;

  const { suggestedTags } = useAppSelector(SearchSelector);
  // const [multiselectValue, setMultiSelectValue] = useState<string[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);

  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [processing, setProcessing] = useState<boolean>(false);

  const [progressText, setProgressText] = useState<string>('');

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [summaryName, setSummaryName] = useState<string | null>('');
  const [videoTags, SetVideoTags] = useState<string | null>('');
  const [chunkDuration, setChunkDuration] = useState<number>(() => defaultChunkDuration);
  const [sampleFrame, setSampleFrame] = useState<number>(() => defaultSampleFrames);

  const [frameOverlap, setFrameOverlap] = useState<number>(defaultOverlap);
  const [multiFrame, setMultiFrame] = useState<number>(0);

  const [framePrompt, setFramePrompt] = useState<string>('');
  const [mapPrompt, setMapPrompt] = useState<string>('');
  const [reducePrompt, setReducePrompt] = useState<string>('');
  const [singleReducePrompt, setSingleReducePrompt] = useState<string>('');

  const [systemConfig, setSystemConfig] = useState<SystemConfigWithMeta>();

  const [audio, setAudio] = useState<boolean>(true);

  const videoFileRef = useRef<HTMLInputElement>(null);
  const videoLabelRef = useRef<HTMLInputElement>(null);
  const selectorRef = useRef<HTMLSelectElement>(null);
  const audioModelRef = useRef<HTMLSelectElement>(null);

  const videoFileInputClick = () => {
    if (!uploading) {
      videoFileRef.current?.click();
    }
  };

  useEffect(() => {
    if (systemConfig) {
      const calculatedMultiFrame = Math.min(sampleFrame + frameOverlap, systemConfig.multiFrame);
      setMultiFrame(calculatedMultiFrame);

      setFramePrompt(systemConfig.framePrompt);
      setMapPrompt(systemConfig.summaryMapPrompt);
      setReducePrompt(systemConfig.summaryReducePrompt);
      setSingleReducePrompt(systemConfig.summarySinglePrompt);
    }
  }, [sampleFrame, frameOverlap, systemConfig]);

  useEffect(() => {
    if (!uploading) {
      resetForm();
      dispatch(UIActions.closePrompt());
    }
  }, []);

  const resetForm = async () => {
    setSelectedFile(null);
    setSummaryName(null);
    setSampleFrame(defaultSampleFrames);
    setChunkDuration(defaultChunkDuration);
    setProgressText('');
    setUploadProgress(0);
    setUploading(false);
    setProcessing(false);
    setSelectedTags([]);
    // setMultiSelectValue([]);
    if (videoFileRef.current) {
      videoFileRef.current.value = '';
    }
    if (videoLabelRef.current) {
      videoLabelRef.current.value = '';
    }

    const res = await axios.get<SystemConfigWithMeta>(`${APP_URL}/app/config`);
    if (res.data) {
      setSystemConfig(res.data);
    }
  };

  useEffect(() => {
    resetForm();
  }, [isOpen]);

  useEffect(() => {
    if (videoLabelRef.current && selectedFile) {
      videoLabelRef.current.value = selectedFile.name;
      setSummaryName(selectedFile.name);
    }
  }, [selectedFile]);

  const frameOverlapChange = (val: number) => {
    setFrameOverlap(val);
    if (systemConfig) {
      const calculatedMultiFrame = Math.min(sampleFrame + val, systemConfig.multiFrame);
      setMultiFrame(calculatedMultiFrame);
    }
  };

  const videoFileChange = (files: FileList | null) => {
    if (files && files.length > 0) {
      setSelectedFile(files[0]);
    } else if (!selectedFile) {
      setSelectedFile(null);
    }
  };

  const uploadVideo = async (videoData: VideoDTO): Promise<AxiosResponse<VideoRO, any>> => {
    const formData = new FormData();

    if (selectedFile) {
      formData.append('video', selectedFile);
    }

    if (videoData.name) {
      formData.append('name', videoData.name);
    }

    if (videoData.tags) {
      formData.append('tags', videoData.tags);
    }

    return await axios.post<VideoRO>(videoUploadAPi, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (ev: AxiosProgressEvent) => {
        setUploadProgress((ev.progress ?? 0) * 100);
      },
    });
  };

  const triggerSummaryPipeline = async (videoId: string): Promise<SummaryPipelinRO | null> => {
    const pipelineData = getSummaryPipelineDTO(videoId);

    try {
      const pipelineRes = await axios.post<SummaryPipelinRO>(summaryApi, pipelineData, {
        headers: { 'Content-Type': 'application/json' },
      });
      return pipelineRes.data;
    } catch (error) {
      if (error) {
        notify('Unable to trigger pipeline', NotificationSeverity.ERROR);
      }
      return null;
    }
  };

  const getSummaryPipelineDTO = (videoId: string): SummaryPipelineDTO => {
    const title = summaryName ?? '';

    const res: SummaryPipelineDTO = {
      evam: { evamPipeline: (selectorRef?.current?.value as EVAMPipelines) ?? EVAMPipelines.OBJECT_DETECTION },
      sampling: {
        chunkDuration: chunkDuration,
        samplingFrame: sampleFrame,
        frameOverlap: frameOverlap,
        multiFrame: systemConfig?.multiFrame ?? 0,
      },
      prompts: {
        framePrompt: framePrompt,
        summaryMapPrompt: mapPrompt,
        summaryReducePrompt: reducePrompt,
        summarySinglePrompt: singleReducePrompt,
      },
      videoId,
      title,
    };

    if (audio && systemConfig?.meta.defaultAudioModel) {
      res.audio = { audioModel: audioModelRef?.current?.value ?? systemConfig.meta.defaultAudioModel };
    }

    if (systemConfig) {
      const systemMultiFrame = systemConfig.multiFrame;
      let multiFrameActual = Math.min(multiFrame, sampleFrame) + frameOverlap;
      multiFrameActual = Math.min(systemMultiFrame, multiFrameActual);
      res.sampling.multiFrame = multiFrameActual;
    }

    return res;
  };

  const fetchUIState = async (stateId: string) => {
    return await axios.get<UIState>(`${stateApi}/${stateId}`);
  };

  const triggerSummary = async () => {
    try {
      setUploading(true);
      setProgressText(t('uploadingVideo'));

      const videoData: VideoDTO = {};

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
        setProgressText(t('TriggeringPipeline'));
        const piplineRes = await triggerSummaryPipeline(videoRes.data.videoId);

        if (piplineRes?.summaryPipelineId) {
          setProgressText(t('fetchingState'));
          const uiState = await fetchUIState(piplineRes.summaryPipelineId);

          if (uiState) {
            dispatch(SummaryActions.addSummary(uiState.data));
            setUploading(false);
            setProgressText(t('allDone'));
            resetForm();
            dispatch(SummaryActions.selectSummary(piplineRes.summaryPipelineId));
            dispatch(VideoChunkActions.setSelectedSummary(piplineRes.summaryPipelineId));
            dispatch(VideoFramesAction.selectSummary(piplineRes.summaryPipelineId));
            dispatch(UIActions.setMux(MuxFeatures.SUMMARY));
            closeDrawer();
          }
        }
      }
    } catch (error: any) {
      console.log('ERROR', error);

      if (error.response && error.response.data && error.response.data.message) {
        notify(error.response.data.message, NotificationSeverity.ERROR);
      }

      // if (error.reponse && error.response.data) {
      //   notify(error.response.data.message, NotificationSeverity.ERROR);
      // } else if (error.request) {
      //   notify(error.request, NotificationSeverity.ERROR);
      // } else if (error instanceof AxiosError && error.message) {
      //   notify(error.message, NotificationSeverity.ERROR);
      // } else {
      //   notify(t('error'), NotificationSeverity.ERROR);
      // }

      setUploading(false);
      setProgressText(t('error'));
      setProcessing(false);
    }

    setUploading(false);
  };

  return (
    <>
      <VideoFormContainer>
        <HiddenFileInput
          type='file'
          onChange={(ev) => videoFileChange(ev.currentTarget.files)}
          ref={videoFileRef}
          accept='.mp4'
        />
        {!selectedFile && <FullWidthButton onClick={videoFileInputClick}>{t('SelectVideo')}</FullWidthButton>}
        {selectedFile && (
          <>
            <h3 className='selected-file-name'>{selectedFile.name}</h3>
            <FullWidthButton onClick={videoFileInputClick} kind='danger--tertiary'>
              {t('changeVideo')}
            </FullWidthButton>
            {suggestedTags && suggestedTags.length > 0 && (
              <MultiSelect
                items={suggestedTags}
                itemToString={(item) => (item ? item : '')}
                // selectedItems={multiselectValue}
                onChange={(data) => {
                  if (data.selectedItems) {
                    setSelectedTags(data.selectedItems);
                    // setMultiSelectValue(data.selectedItems);
                  }
                }}
                id='availabel-tags-selector'
                label={t('availableVideoTags')}
              />
            )}
            <TextInputStyled
              labelText={t('customVideoTags')}
              helperText={t('videoTagsHelperText')}
              onChange={(ev) => {
                SetVideoTags(ev.currentTarget.value);
              }}
              id='videoTags'
            />
            <TextInputStyled
              ref={videoLabelRef}
              onChange={(ev) => {
                setSummaryName(ev.currentTarget.value);
              }}
              labelText={t('summaryTitle')}
              id='summaryname'
            />
            <NumberInputStyled
              step={1}
              min={minDuration}
              value={defaultChunkDuration}
              onChange={(_, { value }) => setChunkDuration(+value)}
              label={t('ChunkDurationLabel')}
              id='sampleFrame'
            />
            <NumberInputStyled
              step={1}
              min={minFrames}
              value={defaultSampleFrames}
              onChange={(_, { value }) => setSampleFrame(+value)}
              label={t('FramePerChunkLabel')}
              id='sampleFrame'
            />
            {systemConfig && (
              <StyledAcc>
                <AccordionItem title={t('IngestionSettings')}>
                  <NumberInputStyled
                    id='overrideMultiFrame'
                    value={frameOverlap}
                    min={0}
                    max={systemConfig.multiFrame}
                    onChange={(_, { value }) => {
                      frameOverlapChange(+value);
                    }}
                    label={t('FramesOverlap')}
                  />
                  <NumberInputStyled
                    id='overrideOverlap'
                    value={multiFrame}
                    max={systemConfig.multiFrame}
                    readOnly={true}
                    label={t('MultiFrame')}
                  />
                  {systemConfig.meta.evamPipelines && (
                    <SelectInputStyled id='evam-pipeline-select' labelText={t('Chunking Pipeline')} ref={selectorRef}>
                      {systemConfig.meta.evamPipelines.map((option) => (
                        <SelectItem text={option.name} value={option.value} />
                      ))}
                    </SelectInputStyled>
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
                      <SelectInputStyled id='audioModelsSelector' labelText={t('AudioModels')} ref={audioModelRef}>
                        {systemConfig.meta.audioModels.map((option) => (
                          <SelectItem text={option.display_name} value={option.model_id} />
                        ))}
                      </SelectInputStyled>
                    )}
                  </AccordionItem>
                )}

                <AccordionItem title={t('PromptSettings')}>
                  <PromptInput
                    label={t('FramePrompt')}
                    infoLabel={t('FramePromptInfo')}
                    defaultVal={systemConfig.framePrompt}
                    description={t('FramePromptDescription')}
                    onChange={(newPrompt: string) => {
                      setFramePrompt(newPrompt);
                    }}
                    reset={() => {
                      if (systemConfig) {
                        setFramePrompt(systemConfig.framePrompt);
                      }
                    }}
                    opener='FRAME_PROMPT'
                    prompt={framePrompt}
                    editHeading={t('FramePromptEditing')}
                  />
                  <PromptInput
                    label={t('SummaryPrompt')}
                    infoLabel={t('SummaryPromptInfo')}
                    defaultVal={systemConfig.summaryMapPrompt}
                    description={t('SummaryPromptDescription')}
                    onChange={(newPrompt: string) => {
                      setMapPrompt(newPrompt);
                    }}
                    reset={() => {
                      if (systemConfig) {
                        setFramePrompt(systemConfig.summaryMapPrompt);
                      }
                    }}
                    opener='MAP_PROMPT'
                    prompt={mapPrompt}
                    editHeading={t('SummaryPromptEditing')}
                  />
                  <PromptInput
                    label={t('SummaryReducePrompt')}
                    infoLabel={t('SummaryReducePromptInfo')}
                    defaultVal={systemConfig.summaryReducePrompt}
                    description={t('SummaryReducePromptDescription')}
                    onChange={(newPrompt: string) => {
                      setReducePrompt(newPrompt);
                    }}
                    reset={() => {
                      if (systemConfig) {
                        setFramePrompt(systemConfig.summaryReducePrompt);
                      }
                    }}
                    editHeading={t('SummaryReducePromptEditing')}
                    opener='REDUCE_PROMPT'
                    prompt={reducePrompt}
                  />
                  <PromptInput
                    label={t('SummarySinglePrompt')}
                    infoLabel={t('SummarySinglePromptInfo')}
                    defaultVal={systemConfig.summarySinglePrompt}
                    description={t('SummarySinglePromptDescription')}
                    onChange={(newPrompt: string) => {
                      setSingleReducePrompt(newPrompt);
                    }}
                    reset={() => {
                      if (systemConfig) {
                        setFramePrompt(systemConfig.summarySinglePrompt);
                      }
                    }}
                    editHeading={t('SummarySinglePromptEditing')}
                    opener='SINGLE_PROMPT'
                    prompt={singleReducePrompt}
                  />
                </AccordionItem>
              </StyledAcc>
            )}
            <MessageBox style={{ marginTop: '1rem' }}>
              {t('sampleRate', {
                frames: sampleFrame,
                interval: chunkDuration,
              })}
            </MessageBox>

            {systemConfig && frameOverlap + sampleFrame > systemConfig.multiFrame && (
              <WarningContainer>
                {t('frameOverlapWarning', {
                  frames: frameOverlap + sampleFrame,
                  maxFrames: systemConfig.multiFrame,
                })}
              </WarningContainer>
            )}
            <FullWidthButton
              onClick={() => {
                if (!uploading) {
                  triggerSummary();
                }
              }}
            >
              {uploading ? t('uploadingVideoState') : t('SummarizeVideo')}
            </FullWidthButton>
            {uploading && (
              <ProgressBar value={uploadProgress} helperText={uploadProgress.toFixed(2) + '%'} label={progressText} />
            )}
            {processing && <ProgressBar label={progressText} />}
          </>
        )}
      </VideoFormContainer>
    </>
  );
};

export default VideoUpload;
