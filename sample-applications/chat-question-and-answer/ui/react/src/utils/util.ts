// Copyright (C) 2024 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import client from "./client";
import { HEALTH_CHECK_URL } from "../config";

export const getCurrentTimeStamp = () => {
  return Math.floor(Date.now() / 1000);
};

export const uuidv4 = () => {
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
    (+c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (+c / 4)))).toString(16),
  );
};

export const isValidUrl = (url: string): boolean => {
  try {
    const parsedUrl = new URL(url);
    return parsedUrl.protocol === 'http:' || parsedUrl.protocol === 'https:';
  } catch {
    return false;
  }
};

/**
 * Extracts the original filename from database naming pattern
 * Pattern: prefix_filename_stringID.extension
 * Example: "doc_my_file_name_abc123.pdf" -> "my_file_name.pdf"
 */
export const extractOriginalFilename = (dbFilename: string): string => {
  if (!dbFilename) return dbFilename;

  // 1. Extract position of last dot and extract extension
  const lastDotIndex = dbFilename.lastIndexOf('.');
  const extension = lastDotIndex !== -1 ? dbFilename.substring(lastDotIndex) : '';

  // 2. Remove prefix (find index of 1st underscore, and truncate everything before that)
  const firstUnderscoreIndex = dbFilename.indexOf('_');
  if (firstUnderscoreIndex === -1) return dbFilename; // No underscore found

  const withoutPrefix = dbFilename.substring(firstUnderscoreIndex + 1);

  // 3. Find the index of last underscore and truncate the string after that
  const nameWithoutExtension = lastDotIndex !== -1 ? withoutPrefix.substring(0, withoutPrefix.lastIndexOf('.')) : withoutPrefix;
  const lastUnderscoreIndex = nameWithoutExtension.lastIndexOf('_');
  if (lastUnderscoreIndex === -1) return dbFilename; // No second underscore found

  const originalFilename = nameWithoutExtension.substring(0, lastUnderscoreIndex);

  // 4. Attach with extension
  return originalFilename + extension;
};

export const checkHealth = async () => {
  try {
    const response = await client.get(HEALTH_CHECK_URL);
    if (response.status === 200) {
      return { status: response.status };
    } else {
      return {
        status: response.status,
        message:
          'LLM model server is not ready to accept connections. Please try after a few minutes.',
      };
    }
  } catch (error) {
    return {
      status: 503,
      message:
        'LLM model server is not ready to accept connections. Please try after a few minutes.',
    };
  }
};
