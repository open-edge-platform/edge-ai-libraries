// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Button, IconButton, Modal, ModalBody, MultiSelect, TextArea } from '@carbon/react';
import { Image as ImageIcon, Close } from '@carbon/icons-react';
import { ChangeEvent, FC, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { SearchAdd, SearchSelector } from '../../redux/search/searchSlice';
import { UIActions } from '../../redux/ui/ui.slice';
import { MuxFeatures } from '../../redux/ui/ui.model';
import { TimeFilterSelection } from '../../redux/search/search';
import TimeFilterControl from '../Search/TimeFilterControl';
import { FEATURE_SEARCH, FEATURE_MUX } from '../../config';
import {
  FEATURE_STATE,
  FeatureMux,
  acceptedImageFormats,
  plainAcceptedImageFormats,
  MAX_IMAGE_SIZE_MB,
  IMAGE_SEARCH_MAX_DIMENSION,
} from '../../utils/constant';

export interface SearchModalProps {
  showModal: boolean;
  closeModal: () => void;
}

// Image search is available only in frame-embedding deployments (--search/--dual).
// The unified deployment (--unified) searches text summaries and is the only mode
// that uses the SUMMARY_SEARCH mux, so derive capability from existing flags
// rather than a dedicated one.
const imageSearchEnabled =
  FEATURE_SEARCH === FEATURE_STATE.ON &&
  FEATURE_MUX !== FeatureMux.SUMMARY_SEARCH;

/**
 * Validate and downscale a user-selected query image to a bounded base64 data URL.
 * Rejects with an i18n key when the file fails a validation check.
 */
const processImageFile = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const extension = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`;
    if (
      !acceptedImageFormats.includes(file.type) ||
      !plainAcceptedImageFormats.includes(extension)
    ) {
      reject('searchImageInvalidType');
      return;
    }

    if (file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024) {
      reject('searchImageTooLarge');
      return;
    }

    const objectUrl = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(objectUrl);
      const scale = Math.min(
        1,
        IMAGE_SEARCH_MAX_DIMENSION / Math.max(img.width, img.height),
      );
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(img.width * scale));
      canvas.height = Math.max(1, Math.round(img.height * scale));
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        reject('searchImageDecodeError');
        return;
      }
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      resolve(canvas.toDataURL('image/jpeg', 0.9));
    };
    img.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject('searchImageDecodeError');
    };
    img.src = objectUrl;
  });

export const SearchModal: FC<SearchModalProps> = ({ showModal, closeModal }) => {
  const { t } = useTranslation();
  const dispatch = useAppDispatch();

  const { suggestedTags } = useAppSelector(SearchSelector);

  const [textInput, setTextInput] = useState<string>('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]); // Placeholder for selected tags if needed
  const [timeFilter, setTimeFilter] = useState<TimeFilterSelection | null>(null);
  const [imageData, setImageData] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  const resetInput = () => {
    setTextInput('');
    setImageData(null);
    setImageError(null);

    if (imageInputRef.current) {
      imageInputRef.current.value = '';
    }
  };

  const handleImageChange = async (ev: ChangeEvent<HTMLInputElement>) => {
    const file = ev.target.files?.[0];
    if (!file) {
      return;
    }
    setImageError(null);
    try {
      const dataUrl = await processImageFile(file);
      setImageData(dataUrl);
    } catch (errKey) {
      setImageData(null);
      setImageError(typeof errKey === 'string' ? errKey : 'searchImageDecodeError');
    } finally {
      // Allow re-selecting the same file after a removal/error.
      if (imageInputRef.current) {
        imageInputRef.current.value = '';
      }
    }
  };

  const removeImage = () => {
    setImageData(null);
    setImageError(null);
    if (imageInputRef.current) {
      imageInputRef.current.value = '';
    }
  };

  const submitSearch = async () => {
    try {
      if (imageData) {
        dispatch(SearchAdd({ image: imageData, tags: selectedTags, timeFilter }));
      } else {
        if (!textInput.trim()) {
          return;
        }
        dispatch(SearchAdd({ query: textInput, tags: selectedTags, timeFilter }));
      }
      dispatch(UIActions.setMux(MuxFeatures.SEARCH));
      resetInput();
      closeModal();
    } catch (err) {
      console.error('Error submitting search:', err);
    }
  };

  return (
    <Modal
      open={showModal}
      onRequestClose={() => {
        closeModal();
      }}
      modalHeading={t('videoSearchStart')}
      primaryButtonText={t('search')}
      secondaryButtonText={t('cancel')}
      primaryButtonDisabled={!imageData && !textInput.trim()}
      onRequestSubmit={() => {
        submitSearch();
      }}
    >
      <ModalBody>
        {/* Hidden file input is always mounted so the upload button can trigger it. */}
        {imageSearchEnabled && (
          <input
            ref={imageInputRef}
            type='file'
            accept={acceptedImageFormats.join(',')}
            style={{ display: 'none' }}
            onChange={handleImageChange}
          />
        )}

        {imageData ? (
          // Image chosen: the preview takes over the text-area's space. Removing it
          // restores the (preserved) typed query, since the text box is controlled.
          <div>
            <div
              style={{
                position: 'relative',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                background: '#f4f4f4',
                borderRadius: '4px',
                padding: '0.5rem',
                minHeight: '120px',
              }}
            >
              <img
                src={imageData}
                alt={t('searchByImage')}
                style={{
                  maxWidth: '100%',
                  maxHeight: '220px',
                  objectFit: 'contain',
                  borderRadius: '4px',
                }}
              />
              <IconButton
                kind='secondary'
                size='sm'
                label={t('searchByImageRemove')}
                onClick={removeImage}
                style={{ position: 'absolute', top: '0.5rem', right: '0.5rem' }}
              >
                <Close />
              </IconButton>
            </div>
            <div
              style={{
                marginTop: '0.25rem',
                fontSize: '0.75rem',
                color: '#6f6f6f',
              }}
            >
              {t('searchByImage')}
            </div>
          </div>
        ) : (
          <>
            <TextArea
              labelText=''
              value={textInput}
              maxLength={250}
              onChange={(ev) => {
                setTextInput(ev.currentTarget.value);
              }}
              placeholder={t('SearchingForPlaceholder')}
            />

            {imageSearchEnabled && (
              <div style={{ marginTop: '1rem' }}>
                <Button
                  kind='tertiary'
                  size='sm'
                  renderIcon={ImageIcon}
                  onClick={() => imageInputRef.current?.click()}
                >
                  {t('searchByImageUpload')}
                </Button>
                <div
                  style={{
                    marginTop: '0.25rem',
                    fontSize: '0.75rem',
                    color: imageError ? '#da1e28' : '#6f6f6f',
                  }}
                  role={imageError ? 'alert' : undefined}
                >
                  {imageError
                    ? t(imageError, { size: MAX_IMAGE_SIZE_MB })
                    : t('searchByImageHelper')}
                </div>
              </div>
            )}
          </>
        )}

        {suggestedTags && suggestedTags.length > 0 && (
          <MultiSelect
            helperText={t('tagsHelperText')}
            items={suggestedTags}
            itemToString={(item) => (item ? item : '')}
            onChange={(data) => {
              if (data.selectedItems) {
                setSelectedTags(data.selectedItems);
              }
            }}
            id='suggest-tags-selector'
            label={t('tagsLabel')}
          />
        )}

        <div style={{ marginTop: '1rem' }}>
          <TimeFilterControl
            timeFilter={timeFilter}
            onChange={setTimeFilter}
            idPrefix='modal-time-filter'
            size='sm'
          />
        </div>
      </ModalBody>
    </Modal>
  );
};
