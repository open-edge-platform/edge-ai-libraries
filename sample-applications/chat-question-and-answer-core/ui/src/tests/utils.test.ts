// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  getCurrentTimeStamp,
  uuidv4,
  getFirstValidString,
  decodeEscapedBytes,
  removeLastTagIfPresent,
  getTitle,
  isValidUrl,
  capitalize,
  checkHealth,
  fetchModelName,
} from '../utils/util.ts';
import client from '../utils/client.ts';

describe('Utility Functions test suite', () => {
  beforeEach(() => {
    vi.spyOn(client, 'get');
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('getCurrentTimeStamp test suite', () => {
    it('should return a number that represents the current timestamp in seconds', () => {
      const timestamp = getCurrentTimeStamp();

      expect(typeof timestamp).toBe('number');
      expect(timestamp).toBeLessThanOrEqual(Math.floor(Date.now() / 1000));
    });
  });

  describe('uuidv4 test suite', () => {
    it('should return a valid UUIDv4 format', () => {
      const uuid = uuidv4();
      const uuidRegex =
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

      expect(uuid).toMatch(uuidRegex);
    });

    it('should return unique UUIDs each time', () => {
      const uuid1 = uuidv4();
      const uuid2 = uuidv4();

      expect(uuid1).not.toEqual(uuid2);
    });
  });

  describe('getFirstValidString test suite', () => {
    it('should return the first valid string', () => {
      expect(
        getFirstValidString(null, undefined, '  ', 'first', 'second'),
      ).toBe('first');
      expect(getFirstValidString('only')).toBe('only');
      expect(getFirstValidString(null, undefined, '')).toBe('');
    });

    it('should return an empty string if no valid string is found', () => {
      const result = getFirstValidString(undefined, null, '  ', '');
      expect(result).toBe('');
    });
  });

  describe('decodeEscapedBytes test suite', () => {
    it('should decode a string with escaped hex values into a readable UTF-8 string', () => {
      expect(decodeEscapedBytes('\\x48\\x65\\x6c\\x6c\\x6f')).toBe('Hello');
      expect(
        decodeEscapedBytes(
          '\\x48\\x65\\x6c\\x6c\\x6f\\x20\\x57\\x6f\\x72\\x6c\\x64',
        ),
      ).toBe('Hello World');
      expect(decodeEscapedBytes('')).toBe('');
    });

    it('should return an empty string if there are no valid escaped bytes', () => {
      expect(decodeEscapedBytes('')).toBe('');
      expect(decodeEscapedBytes('\\xZZ')).toBe('');
    });
  });

  describe('removeLastTagIfPresent test suite', () => {
    it('should remove the last tag if present', () => {
      expect(removeLastTagIfPresent('Hello</s>')).toBe('Hello');
      expect(removeLastTagIfPresent('Hello')).toBe('Hello');
    });
  });

  describe('getTitle test suite', () => {
    it('should truncate the title if it exceeds max length', () => {
      expect(getTitle('Short title')).toBe('Short title');
      expect(
        getTitle('This is a very long title that should be truncated'),
      ).toBe('This is a very long title that should be...');
    });

    it('should handle empty input', () => {
      expect(getTitle('')).toBe('');
    });
  });

  describe('isValidUrl test suite', () => {
    it('should return true for a valid HTTP URL', () => {
      expect(isValidUrl('http://example.com')).toBe(true);
    });

    it('should return true for a valid HTTPS URL', () => {
      expect(isValidUrl('https://example.com')).toBe(true);
    });

    it('should return true for a valid URL with a path', () => {
      expect(isValidUrl('https://example.com/path')).toBe(true);
    });

    it('should return true for a valid URL with query parameters', () => {
      expect(isValidUrl('https://example.com/path?name=value')).toBe(true);
    });

    it('should return true for a valid URL with a fragment', () => {
      expect(isValidUrl('https://example.com/path#fragment')).toBe(true);
    });

    it('should return true for a valid URL with a port', () => {
      expect(isValidUrl('https://example.com:8080')).toBe(true);
    });

    it('should return false for an invalid URL', () => {
      expect(isValidUrl('invalid-url')).toBe(false);
    });

    it('should return false for a string without a protocol', () => {
      expect(isValidUrl('www.example.com')).toBe(false);
    });

    it('should return false for a string with spaces', () => {
      expect(isValidUrl('https:// example .com')).toBe(false);
    });

    it('should return false for an empty string', () => {
      expect(isValidUrl('')).toBe(false);
    });

    it('should return false for a string with only spaces', () => {
      expect(isValidUrl('   ')).toBe(false);
    });

    it('should return false for a URL with an unsupported protocol', () => {
      expect(isValidUrl('ftp://example.com')).toBe(false);
    });

    it('should return true for a URL with special characters', () => {
      expect(isValidUrl('https://example.com/<>')).toBe(true);
    });

    it('should return true for a valid URL with subdomains', () => {
      expect(isValidUrl('https://sub.example.com')).toBe(true);
    });

    it('should return true for a valid URL with a long path', () => {
      expect(isValidUrl('https://example.com/a/very/long/path')).toBe(true);
    });

    it('should return true for a valid URL with multiple query parameters', () => {
      expect(
        isValidUrl('https://example.com/path?name=value&another=value'),
      ).toBe(true);
    });

    it('should return true for a valid URL with a complex structure', () => {
      expect(
        isValidUrl(
          'https://sub.example.com:8080/path/to/resource?name=value#fragment',
        ),
      ).toBe(true);
    });
  });

  describe('capitalize function test suite', () => {
    it('should capitalize the first letter of a lowercase word', () => {
      expect(capitalize('hello')).toBe('Hello');
    });

    it('should capitalize the first letter of an uppercase word', () => {
      expect(capitalize('Hello')).toBe('Hello');
    });

    it('should capitalize the first letter of a word with mixed case', () => {
      expect(capitalize('hElLo')).toBe('HElLo');
    });

    it('should handle an empty string', () => {
      expect(capitalize('')).toBe('');
    });

    it('should capitalize the first letter of a word with special characters', () => {
      expect(capitalize('hello!')).toBe('Hello!');
      expect(capitalize('hello@world')).toBe('Hello@world');
    });

    it('should capitalize the first letter of a word with leading spaces', () => {
      expect(capitalize(' hello')).toBe(' hello');
    });

    it('should capitalize the first letter of a word with trailing spaces', () => {
      expect(capitalize('hello ')).toBe('Hello ');
    });

    it('should capitalize the first letter of a word with numbers', () => {
      expect(capitalize('hello123')).toBe('Hello123');
    });

    it('should capitalize the first letter of a single character', () => {
      expect(capitalize('a')).toBe('A');
      expect(capitalize('A')).toBe('A');
    });

    it('should handle a string with only spaces', () => {
      expect(capitalize('   ')).toBe('   ');
    });

    it('should handle a string with special characters only', () => {
      expect(capitalize('!@#$')).toBe('!@#$');
    });
  });

  describe('checkHealth function test suite', () => {
    it('should return status 200 when the health check is successful', async () => {
      vi.mocked(client.get).mockResolvedValue({ status: 200 });

      const result = await checkHealth();

      expect(result).toEqual({ status: 200 });
    });

    it('should return status and message when the health check fails with non-200 status', async () => {
      vi.mocked(client.get).mockResolvedValue({ status: 500 });

      const result = await checkHealth();

      expect(result).toEqual({
        status: 500
      });
    });

    it('should return status 503 and message when the health check throws an error', async () => {
      vi.mocked(client.get).mockRejectedValue(new Error('Network Error'));

      const result = await checkHealth();

      expect(result).toEqual({
        status: 503
      });
    });
  });

  describe('fetchModelName function test suite', () => {
    it('should return status 200 and llmModel when the model name fetch is successful', async () => {
      vi.mocked(client.get).mockResolvedValue({
        status: 200,
        data: { llm_model: 'Test Model' },
      });

      const result = await fetchModelName();

      expect(result).toEqual({ status: 200, llmModel: 'Test Model' });
    });

    it('should return status and message when the model name fetch fails with non-200 status', async () => {
      vi.mocked(client.get).mockResolvedValue({ status: 404 });

      const result = await fetchModelName();

      expect(result).toEqual({
        status: 404,
        message: 'LLM Model is not set',
      });
    });

    it('should return status 503 and message when the model name fetch throws an error', async () => {
      vi.mocked(client.get).mockRejectedValue(new Error('Network Error'));

      const result = await fetchModelName();

      expect(result).toEqual({
        status: 503,
        message: 'LLM Model is not set',
      });
    });
  });
});
