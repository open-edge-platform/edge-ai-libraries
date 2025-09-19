// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest';
import {
  getCurrentTimeStamp,
  uuidv4,
  getFirstValidString,
  decodeEscapedBytes,
  removeLastTagIfPresent,
  formatDate,
  getTitle,
  extractBetweenDotsWithExtension,
  isValidUrl,
  capitalize,
} from '../utils/util.ts';

describe('Utility Functions test suite', () => {
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

    it('should handle invalid hex characters', () => {
      expect(decodeEscapedBytes('\\xGG\\xHH')).toBe('');
      // When there's a mix of invalid/valid hex, invalid ones are filtered out
      expect(decodeEscapedBytes('\\x99\\xZZ\\x48')).toBe('�H'); // 0x99 produces replacement char, 0xZZ filtered, 0x48 valid
    });

    it('should handle mixed valid and invalid hex values', () => {
      expect(decodeEscapedBytes('\\x48\\xZZ\\x65\\x6c\\x6c\\x6f')).toBe('Hello');
    });
  });

  describe('removeLastTagIfPresent test suite', () => {
    it('should remove the last tag if present', () => {
      expect(removeLastTagIfPresent('Hello</s>')).toBe('Hello');
      expect(removeLastTagIfPresent('Hello')).toBe('Hello');
    });
  });

  describe('formatDate test suite', () => {
    it('should format timestamp correctly', () => {
      const timestamp = new Date('2021-01-01T00:00:00Z').getTime();
      expect(formatDate(timestamp)).toBe('Jan 01, 05:30 AM');
    });

    it('should handle invalid timestamp input', () => {
      expect(() => formatDate(NaN)).toThrow();
    });

    it('should handle zero timestamp', () => {
      expect(() => formatDate(0)).toThrow('Not a number!');
    });

    it('should handle null/undefined timestamp', () => {
      expect(() => formatDate(null as any)).toThrow('Not a number!');
      expect(() => formatDate(undefined as any)).toThrow('Not a number!');
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

  describe('extractBetweenDotsWithExtension test suite', () => {
    it('should extract the filename correctly', () => {
      expect(
        extractBetweenDotsWithExtension('intelgai.filename.osodkaxu.txt'),
      ).toBe('filename.osodkaxu.tx.txt');
    });

    it('should handle input without dots', () => {
      expect(extractBetweenDotsWithExtension('filename')).toBe('filename');
    });

    it('should handle input with only one dot', () => {
      expect(extractBetweenDotsWithExtension('filename.docx')).toBe(
        'filename.doc.docx',
      );
      expect(extractBetweenDotsWithExtension('filename.doc.docx')).toBe(
        'filename.doc.doc.docx',
      );
    });

    it('should handle input with multiple dots', () => {
      expect(
        extractBetweenDotsWithExtension('intelgai.file.osodkaxu.txt'),
      ).toBe('file.osodkaxu.tx.txt');
    });

    it('should handle input with single space without random suffix', () => {
      expect(extractBetweenDotsWithExtension('intelgai.file name.txt')).toBe(
        'file-name.tx.txt',
      );
    });

    it('should handle input with single space with random suffix', () => {
      expect(
        extractBetweenDotsWithExtension('intelgai.file name.osodhcxu.txt'),
      ).toBe('file-name.osodhcxu.tx.txt');
    });

    it('should handle input with multiple hyphens without random suffix', () => {
      expect(extractBetweenDotsWithExtension('intelgai.file - name.txt')).toBe(
        'file---name.tx.txt',
      );
    });

    it('should handle input with multiple hyphens with random suffix', () => {
      expect(
        extractBetweenDotsWithExtension('intelgai.file - name.osofjdls.txt'),
      ).toBe('file---name.osofjdls.tx.txt');
    });

    it('should handle empty input', () => {
      expect(extractBetweenDotsWithExtension('')).toBe('');
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

  describe('capitalize test suite', () => {
    it('should capitalize the first letter of a lowercase word', () => {
      expect(capitalize('hello')).toBe('Hello');
    });

    it('should capitalize the first letter when already capitalized', () => {
      expect(capitalize('Hello')).toBe('Hello');
    });

    it('should handle mixed case strings', () => {
      expect(capitalize('hElLo')).toBe('HElLo');
    });

    it('should handle single character strings', () => {
      expect(capitalize('a')).toBe('A');
      expect(capitalize('A')).toBe('A');
    });

    it('should handle empty string', () => {
      expect(() => capitalize('')).toThrow();
    });

    it('should handle strings starting with non-letters', () => {
      expect(capitalize('123abc')).toBe('123abc');
      expect(capitalize(' hello')).toBe(' hello');
    });
  });
});
