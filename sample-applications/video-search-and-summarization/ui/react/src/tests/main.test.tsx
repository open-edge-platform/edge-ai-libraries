// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Provider } from 'react-redux';
import { StrictMode } from 'react';
import App from '../App.tsx';
import store from '../redux/store.ts';
import { createRoot } from 'react-dom/client';

vi.mock('react-dom/client', () => ({
  createRoot: vi.fn().mockReturnValue({
    render: vi.fn(),
  }),
}));

describe('main component test suite', () => {
  let root: HTMLDivElement;

  beforeEach(() => {
    root = document.createElement('div');
    root.id = 'root';
    document.body.appendChild(root);
  });

  it('should render App component within Provider and StrictMode', async () => {
    await import('../main.tsx');

    expect(createRoot).toHaveBeenCalledWith(root);
    expect(createRoot(root).render).toHaveBeenCalledWith(
      <StrictMode>
        <Provider store={store}>
          <App />
        </Provider>
      </StrictMode>,
    );
  });
});
