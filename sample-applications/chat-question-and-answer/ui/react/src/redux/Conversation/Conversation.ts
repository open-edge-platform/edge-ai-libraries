// Copyright (C) 2024 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export type ConversationRequest = {
  conversationId: string;
  userPrompt: Message;
};
export enum MessageRole {
  Assistant = "assistant",
  User = "user",
  System = "system",
}

export interface Message {
  role: MessageRole;
  content: string;
  time: number;
  conversationId?: string;
}

export interface File {
  file_name: string;
  bucket_name: string;
}

export interface Conversation {
  conversationId: string;
  title?: string;
  Messages: Message[];
  responseStatus?: boolean;
}

export interface ConversationReducer {
  selectedConversationId: string;
  conversations: Conversation[];
  onGoingResults: { [conversationId: string]: string };
  modelName: string;
  files: File[];
  links: string[];
  isGenerating: { [conversationId: string]: boolean };
  isWaitingForFirstToken: { [conversationId: string]: boolean };
  isUploading: boolean;
}
