// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Modal, ModalBody, MultiSelect, TextArea } from '@carbon/react';
import { FC, KeyboardEvent, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { SearchAdd, SearchSelector } from '../../redux/search/searchSlice';
import { UIActions } from '../../redux/ui/ui.slice';
import { MuxFeatures } from '../../redux/ui/ui.model';
import { TimeFilterSelection } from '../../redux/search/search';
import TimeFilterControl from '../Search/TimeFilterControl';

export interface SearchModalProps {
  showModal: boolean;
  closeModal: () => void;
}

export const SearchModal: FC<SearchModalProps> = ({ showModal, closeModal }) => {
  const { t } = useTranslation();
  const dispatch = useAppDispatch();

  const { suggestedTags } = useAppSelector(SearchSelector);

  const [textInput, setTextInput] = useState<string>('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]); // Placeholder for selected tags if needed
  const [timeFilter, setTimeFilter] = useState<TimeFilterSelection | null>(null);
  const [emptyQueryError, setEmptyQueryError] = useState<boolean>(false);
  const textAreaRef = useRef<HTMLTextAreaElement>(null);

  const resetInput = () => {
    setTextInput('');
    setEmptyQueryError(false);

    if (textAreaRef.current) {
      textAreaRef.current.value = '';
    }
  };

  const submitSearch = async () => {
    const query = textInput.trim();

    // Keep the modal open and flag the field instead of running an empty search.
    if (!query) {
      setEmptyQueryError(true);
      textAreaRef.current?.focus();
      return;
    }

    try {
      dispatch(SearchAdd({ query, tags: selectedTags, timeFilter }));
      dispatch(UIActions.setMux(MuxFeatures.SEARCH));
      resetInput();
      closeModal();
    } catch (err) {
      console.error('Error submitting search:', err);
    }
  };

  const handleKeyDown = (ev: KeyboardEvent<HTMLTextAreaElement>) => {
    if (ev.key !== 'Enter' || ev.shiftKey) {
      return;
    }

    // Enter confirms an in-flight IME composition; it must not submit.
    if (ev.nativeEvent.isComposing) {
      return;
    }

    ev.preventDefault();
    void submitSearch();
  };

  return (
    <Modal
      open={showModal}
      onRequestClose={() => {
        setEmptyQueryError(false);
        closeModal();
      }}
      modalHeading={t('videoSearchStart')}
      primaryButtonText={t('search')}
      secondaryButtonText={t('cancel')}
      onRequestSubmit={() => {
        submitSearch();
      }}
      hasScrollingContent
    >
      <ModalBody>
        <TextArea
          labelText=''
          ref={textAreaRef}
          maxLength={250}
          invalid={emptyQueryError}
          invalidText={t('searchQueryRequired')}
          onKeyDown={handleKeyDown}
          onChange={(ev) => {
            setTextInput(ev.currentTarget.value);

            if (ev.currentTarget.value.trim()) {
              setEmptyQueryError(false);
            }
          }}
          placeholder={t('SearchingForPlaceholder')}
        />

        {suggestedTags && suggestedTags.length > 0 && (
          <MultiSelect
            // Let the dropdown menu reposition itself according to the length
            autoAlign
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

        <div style={{ marginTop: '2rem' }}>
          <TimeFilterControl
            timeFilter={timeFilter}
            onChange={setTimeFilter}
            idPrefix='modal-time-filter'
            size='sm'
            // Last field in a scrolling modal body: open upwards so the
            // tooltip is not clipped by the body's bottom edge.
            tooltipAlign='top-start'
          />
        </div>
      </ModalBody>
    </Modal>
  );
};
