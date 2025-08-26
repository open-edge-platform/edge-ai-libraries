// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export const DATA_PREP_URL: string =
  import.meta.env.VITE_DATA_PREP_SERVICE_URL + '/documents';
export const LINK_PREP_URL: string =
  import.meta.env.VITE_DATA_PREP_SERVICE_URL + '/urls';

export const CHAT_QNA_URL: string =
  import.meta.env.VITE_BACKEND_SERVICE_ENDPOINT + '/chat';
export const HEALTH_CHECK_URL: string =
  import.meta.env.VITE_BACKEND_SERVICE_ENDPOINT + '/health';
export const MODEL_URL: string =
  import.meta.env.VITE_BACKEND_SERVICE_ENDPOINT + '/model';
export const MAX_TOKENS: number =
  Number(import.meta.env.VITE_MAX_TOKENS);
