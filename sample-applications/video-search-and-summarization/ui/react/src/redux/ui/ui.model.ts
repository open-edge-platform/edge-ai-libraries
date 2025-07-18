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
}
export interface OpenPromptModal {
  heading: string;
  prompt: string;
  openToken: string;
}
