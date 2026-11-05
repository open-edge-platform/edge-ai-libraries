// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import type { Chunk } from "@/api/console/type";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: Chunk[];
  pending?: string;
  error?: string;
}
export interface CompletionMessage {
  role: "system" | "user" | "assistant";
  content: string;
}
export interface CompletionResponse {
  choices?: {
    delta?: {
      content?: string;
      reasoning?: string;
      reasoning_content?: string;
    };
    message?: { content?: string };
  }[];
  error?: { message: string };
}
