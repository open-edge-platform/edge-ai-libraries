// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

afterEach(() => {
  cleanup();
});

// Global axios mock to prevent network calls in all tests
vi.mock('axios', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ 
      data: {
        videos: [],
        length: 0
      }
    }),
    post: vi.fn().mockResolvedValue({ data: [] }),
    put: vi.fn().mockResolvedValue({ data: [] }),
    delete: vi.fn().mockResolvedValue({ data: [] }),
    patch: vi.fn().mockResolvedValue({ data: [] }),
    request: vi.fn().mockResolvedValue({ data: [] }),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    defaults: {},
  },
}));

// Mock styled-components globally
vi.mock('styled-components', () => {
  // Helper function to filter out styled-component internal props
  const filterProps = (props: any) => {
    const { children, ...otherProps } = props;
    return Object.keys(otherProps).reduce((acc: any, key) => {
      if (!key.startsWith('$')) {
        acc[key] = otherProps[key];
      }
      return acc;
    }, {});
  };

  const mockStyled = new Proxy(() => {}, {
    get: (target: any, prop: any) => {
      if (typeof prop === 'string') {
        return () => {
          const MockComponent = (props: any) => {
            const filteredProps = filterProps(props);
            return React.createElement(prop, filteredProps, props.children);
          };
          MockComponent.displayName = `styled.${prop}`;
          return MockComponent;
        };
      }
      return target[prop];
    },
    apply: (target: any, thisArg: any, argumentsList: any[]) => {
      const [Component] = argumentsList;
      return () => {
        const MockComponent = (props: any) => {
          if (typeof Component === 'string') {
            const filteredProps = filterProps(props);
            return React.createElement(Component, filteredProps, props.children);
          }
          return React.createElement(Component, props);
        };
        MockComponent.displayName = `styled(${Component.displayName || Component.name || 'Component'})`;
        return MockComponent;
      };
    }
  });

  return { 
    default: mockStyled,
    keyframes: vi.fn(() => 'mock-keyframes'),
    __esModule: true
  };
});

// Make sure React is available for the styled-components mock
import React from 'react';
global.React = React;
