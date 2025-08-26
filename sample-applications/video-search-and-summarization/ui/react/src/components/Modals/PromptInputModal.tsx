// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Modal, ModalBody, TextArea } from '@carbon/react';
import { FC, useEffect, useRef, useState } from 'react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { UIActions, uiSelector } from '../../redux/ui/ui.slice';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';

const ErrorContainer = styled.div`
  padding: 1rem;
  width: 100%;
  display: flex;
  flex-flow: row nowrap;
  align-items: center;
  justify-content: flex-start;
  background-color: var(--color-warning);
`;

export const PromptInputModal: FC = () => {
  const { openerToken, modalHeading, modalPrompt, modalPromptVars } = useAppSelector(uiSelector);
  const dispatch = useAppDispatch();

  const { t } = useTranslation();

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const [currentVal, setCurrentVal] = useState<string>('');
  const [unusedVars, setUnusedVars] = useState<string[]>([]);
  const [valid, setValid] = useState<boolean>(false);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.value = modalPrompt;
      setCurrentVal(modalPrompt);
      setValid(true);
    }
  }, [modalPrompt]);

  useEffect(() => {
    if (currentVal) {
      if (modalPromptVars.length > 0) {
        const unUsed: string[] = [];

        for (const promptVar of modalPromptVars) {
          if (!currentVal.includes(promptVar)) {
            unUsed.push(promptVar);
          }
        }
        setValid(unUsed.length === 0);
        setUnusedVars(unUsed);
      } else {
        setValid(true);
        setUnusedVars([]);
      }
    }
  }, [currentVal, modalPromptVars]);

  return (
    <>
      <Modal
        onRequestClose={(_) => {
          dispatch(UIActions.closePrompt());
          if (textareaRef.current) {
            textareaRef.current.defaultValue = '';
            textareaRef.current.value = '';
          }
        }}
        onRequestSubmit={() => {
          if (textareaRef.current && valid) {
            const newPrompt = textareaRef.current.value;
            dispatch(UIActions.submitPromptModal(newPrompt));
          }
        }}
        open={openerToken !== null}
        modalHeading={modalHeading}
        primaryButtonText={t('Submit')}
        secondaryButtonText={t('Cancel')}
        primaryButtonDisabled={!textareaRef.current || !valid}
      >
        <ModalBody>
          {!valid && unusedVars.length > 0 && (
            <ErrorContainer>{t('UnusedVars', { vars: unusedVars.join(',') })}</ErrorContainer>
          )}
          <TextArea
            ref={textareaRef}
            labelText={t('promptInputLabel')}
            onChange={(ev) => {
              setCurrentVal(ev.currentTarget.value);
            }}
            placeholder={t('promptPlaceholder')}
            style={{ height: '30rem', maxHeight: '100rem' }}
          />
        </ModalBody>
      </Modal>
    </>
  );
};

export default PromptInputModal;
