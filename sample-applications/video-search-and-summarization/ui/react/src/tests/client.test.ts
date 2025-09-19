// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from 'vitest';
import axios from 'axios';
import client from '../utils/client';

// Mock axios to ensure we're testing our client module
vi.mock('axios', () => ({
  default: {
    create: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    request: vi.fn(),
    defaults: {},
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() }
    }
  }
}));

describe('Client utility test suite', () => {
  it('should export axios as default', () => {
    expect(client).toBe(axios);
  });

  it('should have all axios methods available', () => {
    expect(typeof client.get).toBe('function');
    expect(typeof client.post).toBe('function');
    expect(typeof client.put).toBe('function');
    expect(typeof client.delete).toBe('function');
    expect(typeof client.request).toBe('function');
  });

  it('should have axios interceptors available', () => {
    expect(client.interceptors).toBeDefined();
    expect(client.interceptors.request).toBeDefined();
    expect(client.interceptors.response).toBeDefined();
    expect(typeof client.interceptors.request.use).toBe('function');
    expect(typeof client.interceptors.response.use).toBe('function');
  });

  it('should have axios defaults object', () => {
    expect(client.defaults).toBeDefined();
    expect(typeof client.defaults).toBe('object');
  });

  it('should allow adding request interceptors', () => {
    const requestInterceptor = vi.fn();
    client.interceptors.request.use(requestInterceptor);
    expect(client.interceptors.request.use).toHaveBeenCalledWith(requestInterceptor);
  });

  it('should allow adding response interceptors', () => {
    const responseInterceptor = vi.fn();
    client.interceptors.response.use(responseInterceptor);
    expect(client.interceptors.response.use).toHaveBeenCalledWith(responseInterceptor);
  });

  it('should support HTTP GET method', () => {
    client.get('/test');
    expect(client.get).toHaveBeenCalledWith('/test');
  });

  it('should support HTTP POST method', () => {
    const data = { test: 'data' };
    client.post('/test', data);
    expect(client.post).toHaveBeenCalledWith('/test', data);
  });

  it('should support HTTP PUT method', () => {
    const data = { test: 'data' };
    client.put('/test', data);
    expect(client.put).toHaveBeenCalledWith('/test', data);
  });

  it('should support HTTP DELETE method', () => {
    client.delete('/test');
    expect(client.delete).toHaveBeenCalledWith('/test');
  });
});
