// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest';
import {
  acceptedFormat,
  plainAcceptedFormat,
  MAX_FILE_SIZE,
  FeatureMux,
  CONFIG_STATE,
  FEATURE_STATE
} from '../utils/constant';

describe('Constants test suite', () => {
  describe('File format constants', () => {
    it('should export acceptedFormat with correct MIME types', () => {
      expect(acceptedFormat).toEqual([
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/plain',
      ]);
    });

    it('should have acceptedFormat as string array', () => {
      expect(Array.isArray(acceptedFormat)).toBe(true);
      acceptedFormat.forEach(format => {
        expect(typeof format).toBe('string');
      });
    });

    it('should export plainAcceptedFormat with correct extensions', () => {
      expect(plainAcceptedFormat).toEqual(['.pdf', '.docx', '.txt']);
    });

    it('should have plainAcceptedFormat as string array', () => {
      expect(Array.isArray(plainAcceptedFormat)).toBe(true);
      plainAcceptedFormat.forEach(format => {
        expect(typeof format).toBe('string');
        expect(format.startsWith('.')).toBe(true);
      });
    });

    it('should have matching number of MIME types and extensions', () => {
      expect(acceptedFormat.length).toBe(plainAcceptedFormat.length);
    });
  });

  describe('File size constants', () => {
    it('should export MAX_FILE_SIZE as number', () => {
      expect(typeof MAX_FILE_SIZE).toBe('number');
      expect(MAX_FILE_SIZE).toBe(10);
    });

    it('should have positive MAX_FILE_SIZE value', () => {
      expect(MAX_FILE_SIZE).toBeGreaterThan(0);
    });
  });

  describe('FeatureMux enum', () => {
    it('should have correct ATOMIC value', () => {
      expect(FeatureMux.ATOMIC).toBe('ATOMIC');
    });

    it('should have correct SEARCH_SUMMARY value', () => {
      expect(FeatureMux.SEARCH_SUMMARY).toBe('SEARCH_SUMMARY');
    });

    it('should have correct SUMMARY_SEARCH value', () => {
      expect(FeatureMux.SUMMARY_SEARCH).toBe('SUMMARY_SEARCH');
    });

    it('should have all enum values as strings', () => {
      Object.values(FeatureMux).forEach(value => {
        expect(typeof value).toBe('string');
      });
    });

    it('should have exactly 3 enum values', () => {
      expect(Object.keys(FeatureMux)).toHaveLength(3);
    });
  });

  describe('CONFIG_STATE enum', () => {
    it('should have correct ON value', () => {
      expect(CONFIG_STATE.ON).toBe('CONFIG_ON');
    });

    it('should have correct OFF value', () => {
      expect(CONFIG_STATE.OFF).toBe('CONFIG_OFF');
    });

    it('should have all enum values as strings', () => {
      Object.values(CONFIG_STATE).forEach(value => {
        expect(typeof value).toBe('string');
      });
    });

    it('should have exactly 2 enum values', () => {
      expect(Object.keys(CONFIG_STATE)).toHaveLength(2);
    });
  });

  describe('FEATURE_STATE enum', () => {
    it('should have correct ON value', () => {
      expect(FEATURE_STATE.ON).toBe('FEATURE_ON');
    });

    it('should have correct OFF value', () => {
      expect(FEATURE_STATE.OFF).toBe('FEATURE_OFF');
    });

    it('should have all enum values as strings', () => {
      Object.values(FEATURE_STATE).forEach(value => {
        expect(typeof value).toBe('string');
      });
    });

    it('should have exactly 2 enum values', () => {
      expect(Object.keys(FEATURE_STATE)).toHaveLength(2);
    });
  });

  describe('Enum integration tests', () => {
    it('should support checking if value exists in FeatureMux', () => {
      const testValue = 'ATOMIC';
      expect(Object.values(FeatureMux)).toContain(testValue);
    });

    it('should support checking if value exists in CONFIG_STATE', () => {
      const testValue = 'CONFIG_ON';
      expect(Object.values(CONFIG_STATE)).toContain(testValue);
    });

    it('should support checking if value exists in FEATURE_STATE', () => {
      const testValue = 'FEATURE_ON';
      expect(Object.values(FEATURE_STATE)).toContain(testValue);
    });

    it('should handle enum comparison correctly', () => {
      const configOn: string = CONFIG_STATE.ON;
      const configOff: string = CONFIG_STATE.OFF;
      const featureOn: string = FEATURE_STATE.ON;
      const featureOff: string = FEATURE_STATE.OFF;
      const atomic: string = FeatureMux.ATOMIC;
      const searchSummary: string = FeatureMux.SEARCH_SUMMARY;
      
      expect(configOn !== configOff).toBe(true);
      expect(featureOn !== featureOff).toBe(true);
      expect(atomic !== searchSummary).toBe(true);
    });
  });
});
