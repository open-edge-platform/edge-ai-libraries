// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
export interface CompletionQueryParams {
  temperature?: number;
  top_p?: number;
  presence_penalty?: number;
  max_completion_tokens?: number;
  max_tokens?: number;
  frequency_penalty?: number;
  do_sample?: boolean;
  seed?: number;
}

export interface ChatQueryParams extends CompletionQueryParams {
  stream: boolean;
}
