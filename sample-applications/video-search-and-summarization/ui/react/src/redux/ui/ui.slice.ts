// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { createSelector, createSlice, PayloadAction } from '@reduxjs/toolkit';
import { MuxFeatures, OpenPromptModal, UISliceState } from './ui.model';
import { RootState } from '../store';
import { SearchAdd } from '../search/searchSlice';

export const initialState: UISliceState = {
  promptEditing: null,
  selectedMux: MuxFeatures.SUMMARY,
  groupByTag: false,
  showVideoGroups: false,
};

export const UISlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    openPromptModal: (state: UISliceState, action: PayloadAction<OpenPromptModal>) => {
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

    setMux: (state: UISliceState, action: PayloadAction<MuxFeatures>) => {
      state.selectedMux = action.payload;
    },

    closePrompt: (state: UISliceState) => {
      state.promptEditing = null;
    },

    toggleGroupByTag: (state: UISliceState) => {
      state.groupByTag = !state.groupByTag;
      state.showVideoGroups = state.groupByTag;
    },

    toggleVideoGroups: (state: UISliceState) => {
      state.showVideoGroups = !state.showVideoGroups;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(SearchAdd.pending, (state) => {
        state.showVideoGroups = false;
        state.groupByTag = false;
      })
      .addCase(SearchAdd.fulfilled, (state) => {
        state.showVideoGroups = false;
        state.groupByTag = false;
      });
  },
});

const selectUIState = (state: RootState) => state.ui;

export const uiSelector = createSelector([selectUIState], (uiState) => ({
  openerToken: uiState.promptEditing?.open ?? null,
  promptSubmitValue: uiState.promptEditing?.submitValue ?? null,
  modalHeading: uiState.promptEditing?.heading ?? '',
  modalPrompt: uiState.promptEditing?.prompt ?? '',
  modalPromptVars: uiState.promptEditing?.vars ?? [],
  selectedMux: uiState.selectedMux,
  groupByTag: uiState.groupByTag,
  showVideoGroups: uiState.showVideoGroups,
}));

export const UIReducer = UISlice.reducer;
export const UIActions = UISlice.actions;