// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import { Provider } from 'react-redux';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import '@testing-library/jest-dom';
import SearchMainContainer from '../components/Search/SearchContainer';
import store from '../redux/store';

// Mock the child components
vi.mock('../components/Search/SearchSidebar', () => ({
  default: () => <div data-testid="search-sidebar">Search Sidebar Component</div>,
}));

vi.mock('../components/Search/SearchContent', () => ({
  default: () => <div data-testid="search-content">Search Content Component</div>,
}));

describe('SearchMainContainer Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render SearchSidebar and SearchContent components', () => {
    render(
      <Provider store={store}>
        <SearchMainContainer />
      </Provider>
    );

    expect(screen.getByTestId('search-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('search-content')).toBeInTheDocument();
  });

  it('should render with fragment wrapper correctly', () => {
    const { container } = render(
      <Provider store={store}>
        <SearchMainContainer />
      </Provider>
    );

    // Should have both child components
    expect(screen.getByTestId('search-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('search-content')).toBeInTheDocument();
    expect(container.children).toHaveLength(2);
  });

  it('should export as default', () => {
    expect(SearchMainContainer).toBeDefined();
    expect(typeof SearchMainContainer).toBe('function');
  });

  it('should handle component rendering consistently', () => {
    const { rerender } = render(
      <Provider store={store}>
        <SearchMainContainer />
      </Provider>
    );

    expect(screen.getByTestId('search-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('search-content')).toBeInTheDocument();

    rerender(
      <Provider store={store}>
        <SearchMainContainer />
      </Provider>
    );

    expect(screen.getByTestId('search-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('search-content')).toBeInTheDocument();
  });

  it('should maintain component structure', () => {
    const { container } = render(
      <Provider store={store}>
        <SearchMainContainer />
      </Provider>
    );

    expect(screen.getByTestId('search-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('search-content')).toBeInTheDocument();
    expect(container.children).toHaveLength(2);
  });

  it('should render components in correct order', () => {
    const { container } = render(
      <Provider store={store}>
        <SearchMainContainer />
      </Provider>
    );

    const children = Array.from(container.children);
    expect(children[0]).toHaveAttribute('data-testid', 'search-sidebar');
    expect(children[1]).toHaveAttribute('data-testid', 'search-content');
  });
});
