// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock socket.io-client before importing the module
const mockIo = vi.fn();
vi.mock('socket.io-client', () => ({
  io: mockIo
}));

// Mock the config and constants
vi.mock('../config', () => ({
  APP_URL: 'http://localhost:8080',
  SOCKET_APPEND: 'CONFIG_ON'
}));

vi.mock('../utils/constant', () => ({
  CONFIG_STATE: {
    ON: 'CONFIG_ON',
    OFF: 'CONFIG_OFF'
  }
}));

describe('Socket configuration test suite', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Clear console logs
    vi.spyOn(console, 'log').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should create socket with default configuration when SOCKET_APPEND is OFF', async () => {
    // Mock SOCKET_APPEND as OFF
    vi.doMock('../config', () => ({
      APP_URL: 'http://localhost:8080',
      SOCKET_APPEND: 'CONFIG_OFF'
    }));

    const mockSocket = { id: 'test-socket-default' };
    mockIo.mockReturnValue(mockSocket);

    // Dynamically import to get fresh module with mocked config
    const socketModule = await import('../socket');

    expect(mockIo).toHaveBeenCalledWith({ path: '/ws/' });
    expect(socketModule.socket).toBe(mockSocket);
  });

  it('should create socket with APP_URL when SOCKET_APPEND is ON', async () => {
    // Mock SOCKET_APPEND as ON
    vi.doMock('../config', () => ({
      APP_URL: 'http://localhost:8080',
      SOCKET_APPEND: 'CONFIG_ON'
    }));

    const mockSocket = { id: 'test-socket-with-url' };
    mockIo.mockReturnValue(mockSocket);

    // Clear module cache and re-import
    vi.resetModules();
    const socketModule = await import('../socket');

    expect(mockIo).toHaveBeenCalledWith('http://localhost:8080', { path: '/ws/' });
    expect(socketModule.socket).toBe(mockSocket);
  });

  it('should log configuration values', async () => {
    const consoleSpy = vi.spyOn(console, 'log');
    
    // Re-import the module to trigger the console.log calls
    vi.resetModules();
    await import('../socket');

    expect(consoleSpy).toHaveBeenCalledWith('Append', expect.any(String));
    expect(consoleSpy).toHaveBeenCalledWith('URL', expect.any(String));
  });

  it('should export socket instance', async () => {
    const mockSocket = { id: 'test-socket-export' };
    mockIo.mockReturnValue(mockSocket);

    vi.resetModules();
    const socketModule = await import('../socket');

    expect(socketModule.socket).toBeDefined();
    expect(socketModule.socket).toBe(mockSocket);
  });
});
