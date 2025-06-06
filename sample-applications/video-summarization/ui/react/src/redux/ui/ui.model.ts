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
