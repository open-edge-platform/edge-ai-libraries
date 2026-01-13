// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
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

export const processMD = (message: string): string => {
  message = message.replace('```markdown', '');
  return message;
};

/**
 * Formats a date into yyyyMMdd_HHmm format
 * @param date - The date to format
 * @returns Formatted date string
 */
export const formatDateForFilename = (date: Date): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${year}${month}${day}_${hours}${minutes}`;
};

/**
 * Sanitizes a string for use in filenames
 * @param str - The string to sanitize
 * @returns Sanitized string
 */
export const sanitizeFilename = (str: string): string => {
  return str.replace(/[^a-z0-9_-]/gi, '_');
};

/**
 * Downloads text content as a Markdown file
 * @param content - The text content to download
 * @param filename - The name of the file to download
 * @throws Error if download fails
 */
export const downloadTextFile = (content: string, filename: string): void => {
  try {
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch (error) {
    console.error('Download failed:', error);
    throw new Error('Failed to download file. Please try again.');
  }
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

export const formatDate = (timestamp: number) => {
  if (!timestamp) {
    throw new Error('Not a number!');
  }

  if (!timestamp) {
    throw new Error('Not a number!');
  }

  const date = new Date(timestamp);
  return date.toLocaleString('en-US', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  });
};

export const getTitle = (input: string): string => {
  const maxLength = 40;
  if (input.length <= maxLength) return input;
  return input.slice(0, maxLength) + '...';
};

export const extractBetweenDotsWithExtension = (input: string): string => {
  if (!input) {
    return '';
  }
  if (input.startsWith('intelgai')) {
    input = input.slice('intelgai'.length + 1);
  }

  const lastHyphenIndex = input.lastIndexOf('_');
  const lastDotIndex = input.lastIndexOf('.');

  const extension = input.slice(lastDotIndex);
  const betweenDots = input.slice(0, lastHyphenIndex);

  // Replace spaces with hyphens in betweenDots
  const updatedBetweenDots = betweenDots.replace(/\s+/g, '-');

  return `${updatedBetweenDots}${extension}`;
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
  return input[0].toUpperCase() + input.slice(1);
};
