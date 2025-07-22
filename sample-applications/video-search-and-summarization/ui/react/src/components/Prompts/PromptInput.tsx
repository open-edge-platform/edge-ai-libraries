// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { IconButton, Toggletip, ToggletipButton, ToggletipContent } from '@carbon/react';
import { FC, useEffect } from 'react';
import styled from 'styled-components';
import { Edit, Information, Reset } from '@carbon/icons-react';
import { useTranslation } from 'react-i18next';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { UIActions, uiSelector } from '../../redux/ui/ui.slice';

export interface PromptInputProps {
  label: string;
  defaultVal: string;
  prompt: string;
  infoLabel: string;
  description: string;
  opener: string;
  editHeading: string;
  onChange: (overridePrompt: string) => void;
  reset: () => void;
}

const PromptInputContainer = styled.div`
  display: flex;
  flex-flow: row wrap;
  align-items: center;
  justify-content: flex-start;
  margin-top: 1rem;
`;
export const PromptInput: FC<PromptInputProps> = ({
  label,
  defaultVal,
  onChange,
  reset,
  editHeading,
  description,
  infoLabel,
  opener,
  prompt,
}) => {
  const { t } = useTranslation();

  const { openerToken, promptSubmitValue } = useAppSelector(uiSelector);

  const dispatch = useAppDispatch();

  useEffect(() => {
    if (promptSubmitValue && openerToken === opener) {
      onChange(promptSubmitValue);
      dispatch(UIActions.closePrompt());
    }
  }, [promptSubmitValue]);

  const onEditHandler = () => {
    dispatch(
      UIActions.openPromptModal({
        heading: editHeading,
        openToken: opener,
        prompt,
      }),
    );
  };

  return (
    <>
      <PromptInputContainer>
        {label}
        <span className='spacer'></span>

        {defaultVal !== prompt && (
          <IconButton size='sm' kind='ghost' label={t('ResetDefault')} onClick={() => reset()}>
            <Reset />
          </IconButton>
        )}
        <IconButton label={t('editPrompt')} onClick={() => onEditHandler()} size='sm' kind='ghost'>
          <Edit />
        </IconButton>
        <Toggletip autoAlign>
          <ToggletipButton label={infoLabel}>
            <Information />
          </ToggletipButton>
          <ToggletipContent>
            <p>{description}</p>
            <hr />
            <h4>{t('promptHeading')}</h4>
            <p>{prompt}</p>
          </ToggletipContent>
        </Toggletip>
      </PromptInputContainer>
    </>
  );
};
