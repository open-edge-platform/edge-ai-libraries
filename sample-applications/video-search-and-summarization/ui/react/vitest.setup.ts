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
  const mockStyled = new Proxy(() => {}, {
    get: (target, prop) => {
      if (typeof prop === 'string') {
        return (templateStrings, ...args) => {
          const MockComponent = (props) => {
            const { children, ...otherProps } = props;
            // Filter out styled-component internal props that start with $
            const filteredProps = Object.keys(otherProps).reduce((acc, key) => {
              if (!key.startsWith('$')) {
                acc[key] = otherProps[key];
              }
              return acc;
            }, {});
            return React.createElement(prop, filteredProps, children);
          };
          MockComponent.displayName = `styled.${prop}`;
          return MockComponent;
        };
      }
      return target[prop];
    },
    apply: (target, thisArg, argumentsList) => {
      const [Component] = argumentsList;
      if (typeof Component === 'string') {
        return (templateStrings, ...args) => {
          const MockComponent = (props) => {
            const { children, ...otherProps } = props;
            // Filter out styled-component internal props that start with $
            const filteredProps = Object.keys(otherProps).reduce((acc, key) => {
              if (!key.startsWith('$')) {
                acc[key] = otherProps[key];
              }
              return acc;
            }, {});
            return React.createElement(Component, filteredProps, children);
          };
          MockComponent.displayName = `styled(${Component})`;
          return MockComponent;
        };
      }
      // For component styled(Component)
      return (templateStrings, ...args) => {
        const MockComponent = (props) => React.createElement(Component, props);
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

// Mock component for Carbon components
const MockComponent2 = React.forwardRef<any, any>((props: any, ref: any) => {
  const { children, ...otherProps } = props;
  // Filter out styled-component internal props that start with $
  const filteredProps = Object.keys(otherProps).reduce((acc, key) => {
    if (!key.startsWith('$')) {
      acc[key] = otherProps[key];
    }
    return acc;
  }, {});
  return React.createElement('div', { ...filteredProps, ref }, children);
});
