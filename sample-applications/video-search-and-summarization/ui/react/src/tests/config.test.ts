// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect } from 'vitest';
import * as config from '../config';

describe('Config Module', () => {
  it('should export APP_URL as a string', () => {
    expect(typeof config.APP_URL).toBe('string');
    expect(config.APP_URL).toBeDefined();
  });

  it('should export ASSETS_ENDPOINT as a string', () => {
    expect(typeof config.ASSETS_ENDPOINT).toBe('string');
    expect(config.ASSETS_ENDPOINT).toBeDefined();
  });

  it('should export SOCKET_APPEND as a string', () => {
    expect(typeof config.SOCKET_APPEND).toBe('string');
    expect(config.SOCKET_APPEND).toBeDefined();
  });

  it('should export FEATURE_SUMMARY as a string', () => {
    expect(typeof config.FEATURE_SUMMARY).toBe('string');
    expect(config.FEATURE_SUMMARY).toBeDefined();
  });

  it('should export FEATURE_SEARCH as a string', () => {
    expect(typeof config.FEATURE_SEARCH).toBe('string');
    expect(config.FEATURE_SEARCH).toBeDefined();
  });

  it('should export FEATURE_MUX as a string', () => {
    expect(typeof config.FEATURE_MUX).toBe('string');
    expect(config.FEATURE_MUX).toBeDefined();
  });

  it('should export all required config constants', () => {
    // Verify all expected exports are present
    expect(config).toHaveProperty('APP_URL');
    expect(config).toHaveProperty('ASSETS_ENDPOINT');
    expect(config).toHaveProperty('SOCKET_APPEND');
    expect(config).toHaveProperty('FEATURE_SUMMARY');
    expect(config).toHaveProperty('FEATURE_SEARCH');
    expect(config).toHaveProperty('FEATURE_MUX');
  });

  it('should have exactly 6 exported constants', () => {
    const exportedKeys = Object.keys(config);
    expect(exportedKeys).toHaveLength(6);
    expect(exportedKeys).toEqual(
      expect.arrayContaining([
        'APP_URL',
        'ASSETS_ENDPOINT',
        'SOCKET_APPEND',
        'FEATURE_SUMMARY',
        'FEATURE_SEARCH',
        'FEATURE_MUX'
      ])
    );
  });

  it('should have non-empty string values', () => {
    // All config values should be non-empty strings
    expect(config.APP_URL).not.toBe('');
    expect(config.ASSETS_ENDPOINT).not.toBe('');
    expect(config.SOCKET_APPEND).not.toBe('');
    expect(config.FEATURE_SUMMARY).not.toBe('');
    expect(config.FEATURE_SEARCH).not.toBe('');
    expect(config.FEATURE_MUX).not.toBe('');
  });

  it('should have consistent export types', () => {
    // All exports should be strings
    expect(typeof config.APP_URL).toBe('string');
    expect(typeof config.ASSETS_ENDPOINT).toBe('string');
    expect(typeof config.SOCKET_APPEND).toBe('string');
    expect(typeof config.FEATURE_SUMMARY).toBe('string');
    expect(typeof config.FEATURE_SEARCH).toBe('string');
    expect(typeof config.FEATURE_MUX).toBe('string');
  });

  it('should validate feature flag naming pattern', () => {
    // Feature constants should start with appropriate prefix
    expect(config.FEATURE_SUMMARY).toMatch(/^(APP_|true|false|enabled|disabled)/);
    expect(config.FEATURE_SEARCH).toMatch(/^(APP_|true|false|enabled|disabled)/);
    expect(config.FEATURE_MUX).toMatch(/^(APP_|true|false|enabled|disabled)/);
  });

  it('should validate URL patterns where applicable', () => {
    // APP_URL and ASSETS_ENDPOINT should look like URLs or placeholder values
    expect(config.APP_URL).toMatch(/^(https?:\/\/|APP_|localhost|\/)/);
    expect(config.ASSETS_ENDPOINT).toMatch(/^(https?:\/\/|APP_|localhost|\/)/);
  });

  it('should validate socket append pattern', () => {
    // SOCKET_APPEND should be a path or placeholder
    expect(config.SOCKET_APPEND).toMatch(/^(\/|APP_)/);
  });
});
