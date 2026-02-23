// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { vi, afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// @ts-expect-error: ResizeObserver is not in jsdom; we provide a test-time mock
if (typeof globalThis.ResizeObserver === 'undefined') {
  // @ts-expect-error: Assigning our mock to the global ResizeObserver constructor
  globalThis.ResizeObserver = MockResizeObserver;
}

afterEach(() => {
  cleanup();
});

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});
