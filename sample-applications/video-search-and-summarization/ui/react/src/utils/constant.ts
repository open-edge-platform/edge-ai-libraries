// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
export const acceptedFormat: string[] = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
];
export const plainAcceptedFormat: string[] = ['.pdf', '.docx', '.txt'];
export const MAX_FILE_SIZE: number = 10;

export enum FeatureMux {
  ATOMIC = 'ATOMIC',
  SEARCH_SUMMARY = 'SEARCH_SUMMARY',
  SUMMARY_SEARCH = 'SUMMARY_SEARCH',
}

export enum CONFIG_STATE {
  ON = 'CONFIG_ON',
  OFF = 'CONFIG_OFF',
}

export enum FEATURE_STATE {
  ON = 'FEATURE_ON',
  OFF = 'FEATURE_OFF',
}
