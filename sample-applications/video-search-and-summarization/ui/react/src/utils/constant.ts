// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
export const acceptedFormat: string[] = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
];
export const plainAcceptedFormat: string[] = ['.pdf', '.docx', '.txt'];
export const MAX_FILE_SIZE: number = 10;

// Image-based search query constraints (UI-side validation).
export const acceptedImageFormats: string[] = [
  'image/jpeg',
  'image/png',
];
export const plainAcceptedImageFormats: string[] = [
  '.jpg',
  '.jpeg',
  '.png',
];
export const MAX_IMAGE_SIZE_MB: number = 2;
// Longest edge (px) the query image is downscaled to before base64 encoding,
// to bound request payload size.
export const IMAGE_SEARCH_MAX_DIMENSION: number = 512;

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
