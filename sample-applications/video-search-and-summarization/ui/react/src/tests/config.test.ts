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

  // FEATURE_CAMERA_CONFIG and NVR_API_BASE drive the NVR camera-configuration
  // modal. They are unused by this app's own compose files but are set by the
  // Metro AI Suite "Live Video Search" deployment, which ships this same UI
  // image. Removing or renaming them silently breaks that app, so they are
  // asserted here explicitly.
  it('should export FEATURE_CAMERA_CONFIG as a string', () => {
    expect(typeof config.FEATURE_CAMERA_CONFIG).toBe('string');
    expect(config.FEATURE_CAMERA_CONFIG).toBeDefined();
  });

  it('should export NVR_API_BASE as a string', () => {
    expect(typeof config.NVR_API_BASE).toBe('string');
    expect(config.NVR_API_BASE).toBeDefined();
  });

  it('should export all required config constants', () => {
    // Verify all expected exports are present
    expect(config).toHaveProperty('APP_URL');
    expect(config).toHaveProperty('ASSETS_ENDPOINT');
    expect(config).toHaveProperty('SOCKET_APPEND');
    expect(config).toHaveProperty('FEATURE_SUMMARY');
    expect(config).toHaveProperty('FEATURE_SEARCH');
    expect(config).toHaveProperty('FEATURE_MUX');
    expect(config).toHaveProperty('FEATURE_CAMERA_CONFIG');
    expect(config).toHaveProperty('NVR_API_BASE');
    expect(config).toHaveProperty('FEATURE_LIVE_STREAMS');
  });

  it('should export FEATURE_LIVE_STREAMS as a string', () => {
    expect(typeof config.FEATURE_LIVE_STREAMS).toBe('string');
    expect(config.FEATURE_LIVE_STREAMS).toBeDefined();
  });

  it('should have exactly 9 exported constants', () => {
    const exportedKeys = Object.keys(config);
    expect(exportedKeys).toHaveLength(9);
    expect(exportedKeys).toEqual(
      expect.arrayContaining([
        'APP_URL',
        'ASSETS_ENDPOINT',
        'SOCKET_APPEND',
        'FEATURE_SUMMARY',
        'FEATURE_SEARCH',
        'FEATURE_MUX',
        'FEATURE_CAMERA_CONFIG',
        'NVR_API_BASE',
        'FEATURE_LIVE_STREAMS'
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
