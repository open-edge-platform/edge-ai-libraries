import { Button, MultiSelect, ProgressBar, TextInput } from '@carbon/react';
import axios, { AxiosProgressEvent, AxiosResponse } from 'axios';
import { FC, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import { APP_URL } from '../../config';
import { UIActions } from '../../redux/ui/ui.slice';
import { NotificationSeverity, notify } from '../Notification/notify';
import { VideoDTO, VideoRO } from '../../redux/video/video';
import { videosLoad } from '../../redux/video/videoSlice';
import { useAppDispatch, useAppSelector } from '../../redux/store';
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
  margin-top: 1rem;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  justify-content: center;
`;

const TextInputStyled = styled(TextInput)`
  margin-top: 1rem;
`;

const HiddenFileInput = styled.input`
  display: none;
`;

export const VideoUploadSearch: FC<VideoUploadProps> = ({ closeDrawer, isOpen }) => {
  const { t } = useTranslation();

  const dispatch = useAppDispatch();
  const videoUploadAPi = `${APP_URL}/videos`;

  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [processing, setProcessing] = useState<boolean>(false);

  const [progressText, setProgressText] = useState<string>('');

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [videoTags, SetVideoTags] = useState<string | null>('');

  const videoFileRef = useRef<HTMLInputElement>(null);
  const videoLabelRef = useRef<HTMLInputElement>(null);

  const { suggestedTags } = useAppSelector(SearchSelector);
  // const [multiselectValue, setMultiSelectValue] = useState<string[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);

  const videoFileInputClick = () => {
    if (!uploading) {
      videoFileRef.current?.click();
    }
  };

  useEffect(() => {
    if (!uploading) {
      resetForm();
      dispatch(UIActions.closePrompt());
    }
  }, []);

  const resetForm = async () => {
    setSelectedFile(null);
    setProgressText('');
    setUploadProgress(0);
    setUploading(false);
    setProcessing(false);
    if (videoFileRef.current) {
      videoFileRef.current.value = '';
    }
    if (videoLabelRef.current) {
      videoLabelRef.current.value = '';
    }
  };

  useEffect(() => {
    resetForm();
  }, [isOpen]);

  useEffect(() => {
    if (videoLabelRef.current && selectedFile) {
      videoLabelRef.current.value = selectedFile.name;
    }
  }, [selectedFile]);

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

  const triggerEmbeddings = async (videoId: string) => {
    const api = [videoUploadAPi, 'search-embeddings', videoId].join('/');
    const res = await axios.post<{ status: string; message: string }>(api);
    return res.data;
  };

  const triggerSearch = async () => {
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
        setProgressText(t('CreatingEmbeddings'));

        const embeddingRes = await triggerEmbeddings(videoRes.data.videoId);

        if (embeddingRes.status === 'success') {
          setProgressText(t('allDone'));
          setUploading(false);
          resetForm();
          closeDrawer();
        }
      }
    } catch (error: any) {
      console.log('ERROR', error);
      if (error.reponse && error.response.data) {
        notify(error.response.data.message, NotificationSeverity.ERROR);
      }
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

            <FullWidthButton
              onClick={() => {
                if (!uploading) {
                  triggerSearch();
                }
              }}
            >
              {uploading ? t('uploadingVideoState') : t('AddVideoToEmbedding')}
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

export default VideoUploadSearch;
