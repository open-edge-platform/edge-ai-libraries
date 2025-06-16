import { Modal, ModalBody, TextArea } from '@carbon/react';
import { FC, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAppDispatch } from '../../redux/store';
import { SearchAdd } from '../../redux/search/searchSlice';

export interface SearchModalProps {
  showModal: boolean;
  closeModal: () => void;
}

export const SearchModal: FC<SearchModalProps> = ({ showModal, closeModal }) => {
  const { t } = useTranslation();
  const dispatch = useAppDispatch();

  const [textInput, setTextInput] = useState<string>('');
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
      dispatch(SearchAdd(query));
      resetInput();
      closeModal();
    } catch (err) {}
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
      </ModalBody>
    </Modal>
  );
};
