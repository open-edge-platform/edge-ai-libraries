import { createSelector, createSlice, PayloadAction } from '@reduxjs/toolkit';
import { OpenPromptModal, UISliceState } from './ui.model';
import { RootState } from '../store';

export const initialState: UISliceState = {
  promptEditing: null,
};

export const UISlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    openPromptModal: (
      state: UISliceState,
      action: PayloadAction<OpenPromptModal>,
    ) => {
      const { heading, openToken, prompt } = action.payload;

      const vars: Set<string> = new Set();

      const varsReg = new RegExp(/%\w+%/, 'gi');

      if (prompt) {
        const matches = prompt.matchAll(varsReg);
        for (const match of matches) {
          vars.add(match[0]);
        }
      }

      state.promptEditing = {
        open: openToken,
        heading,
        prompt,
        submitValue: null,
        vars: Array.from(vars),
      };
    },

    submitPromptModal: (state: UISliceState, action: PayloadAction<string>) => {
      if (state.promptEditing) {
        state.promptEditing.submitValue = action.payload;
      }
    },

    closePrompt: (state: UISliceState) => {
      state.promptEditing = null;
    },
  },
});

const selectUIState = (state: RootState) => state.ui;

export const uiSelector = createSelector([selectUIState], (uiState) => ({
  openerToken: uiState.promptEditing?.open ?? null,
  promptSubmitValue: uiState.promptEditing?.submitValue ?? null,
  modalHeading: uiState.promptEditing?.heading ?? '',
  modalPrompt: uiState.promptEditing?.prompt ?? '',
  modalPromptVars: uiState.promptEditing?.vars ?? [],
}));

export const UIReducer = UISlice.reducer;
export const UIActions = UISlice.actions;
