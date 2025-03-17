// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export enum MessageRole {
  Assistant = 'assistant',
  User = 'user',
  System = 'system',
}

export interface Message {
  role: MessageRole;
  content: string;
  time: number;
  conversationId: string;
}

export interface ConversationRequest {
  userPrompt: Message;
}

export interface Conversation {
  conversationId: string;
  title?: string;
  messages: Message[];
  responseStatus: boolean;
}

export interface File {
  bucket_name: string;
  file_name: string;
}

export interface ConversationReducer {
  selectedConversationId: string;
  conversations: Conversation[];
  onGoingResult: string;
  files: File[];
  links: string[];
  isGenerating: boolean;
}
