// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export interface PromptEditing {
  open: string;
  heading: string;
  prompt: string;
  submitValue: string | null;
  vars: string[];
}

export interface UISliceState {
  promptEditing: PromptEditing | null;
}
export interface OpenPromptModal {
  heading: string;
  prompt: string;
  openToken: string;
}
