// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Modal, ModalBody, MultiSelect, TextArea } from '@carbon/react';
import { FC, useRef, useState } from 'react';
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
  const textAreaRef = useRef<HTMLTextAreaElement>(null);

  const resetInput = () => {
    setTextInput('');

    if (textAreaRef.current) {
      textAreaRef.current.value = '';
    }
  };

  const submitSearch = async () => {
    try {
      const query = textInput;
      dispatch(SearchAdd({ query, tags: selectedTags, timeFilter }));
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
      onRequestSubmit={() => {
        submitSearch();
      }}
    >
      <ModalBody>
        <TextArea
          labelText=''
          ref={textAreaRef}
          maxLength={250}
          onChange={(ev) => {
            setTextInput(ev.currentTarget.value);
          }}
          placeholder={t('SearchingForPlaceholder')}
        />

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
