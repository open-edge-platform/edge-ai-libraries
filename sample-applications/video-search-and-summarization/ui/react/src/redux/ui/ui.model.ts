// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
export interface PromptEditing {
  open: string;
  heading: string;
  prompt: string;
  submitValue: string | null;
  vars: string[];
}

export enum MuxFeatures {
  SEARCH,
  SUMMARY,
}

export interface UISliceState {
  promptEditing: PromptEditing | null;
  selectedMux: MuxFeatures;
  groupByTag: boolean;
  showVideoGroups: boolean;
}
export interface OpenPromptModal {
  heading: string;
  prompt: string;
  openToken: string;
}