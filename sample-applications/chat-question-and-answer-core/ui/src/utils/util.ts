// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { HEALTH_CHECK_URL, MODEL_URL } from '../config.ts';
import client from './client.ts';

export const getCurrentTimeStamp = () => {
  return Math.floor(Date.now() / 1000);
};

export const uuidv4 = () => {
  return '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, (c) =>
    (
      +c ^
      (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (+c / 4)))
    ).toString(16),
  );
};

export const getFirstValidString = (
  ...args: (string | undefined | null)[]
): string => {
  for (const arg of args) {
    if (arg !== null && arg !== undefined && arg.trim() !== '') {
      return arg;
    }
  }
  return '';
};

// Decode \x hexadecimal encoding
export const decodeEscapedBytes = (str: string): string => {
  const byteArray: number[] = str
    .split('\\x')
    .slice(1)
    .map((byte: string) => {
      const parsedByte = parseInt(byte, 16);
      return isNaN(parsedByte) ? -1 : parsedByte;
    })
    .filter((byte) => byte >= 0);

  if (byteArray.length === 0) return '';

  return new TextDecoder('utf-8').decode(new Uint8Array(byteArray));
};

export const removeLastTagIfPresent = (message: string): string => {
  if (message.trim().endsWith('</s>')) {
    return message.substring(0, message.length - 4).trim();
  }
  return message;
};

export const getTitle = (input: string): string => {
  const maxLength = 40;
  if (input.length <= maxLength) return input;
  return input.slice(0, maxLength) + '...';
};

export const isValidUrl = (url: string): boolean => {
  try {
    const parsedUrl = new URL(url);
    return parsedUrl.protocol === 'http:' || parsedUrl.protocol === 'https:';
  } catch {
    return false;
  }
};

export const capitalize = (input: string): string => {
  if (input.length === 0) {
    return '';
  }
  return input[0].toUpperCase() + input.slice(1);
};

export const checkHealth = async () => {
  try {
    const response = await client.get(HEALTH_CHECK_URL);
    return { status: response.status };
  } catch (error) {
    return { status: 503 };
  }
};

export const fetchModelName = async () => {
  try {
    const { status, data } = await client.get(MODEL_URL);
    return status === 200
      ? { status, llmModel: data.llm_model }
      : { status, message: 'LLM Model is not set' };
  } catch {
    return { status: 503, message: 'LLM Model is not set' };
  }
};
