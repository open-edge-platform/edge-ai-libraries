// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { Provider, useDispatch, useSelector } from 'react-redux';
import { I18nextProvider } from 'react-i18next';
import { configureStore } from '@reduxjs/toolkit';

import Textarea from '../components/Textarea/Textarea.tsx';
import conversationReducer from '../redux/conversation/conversationSlice.ts';
import i18n from '../utils/i18n';
import {
  notify,
  NotificationSeverity,
} from '../components/Notification/notify.ts';

vi.mock('react-redux', async () => {
  const actual = await vi.importActual('react-redux');
  return {
    ...actual,
    useDispatch: vi.fn(),
    useSelector: vi.fn(),
  };
});

vi.mock('../redux/conversation/conversationSlice.ts', async () => {
  const actual = await vi.importActual(
    '../redux/conversation/conversationSlice.ts',
  );
  return {
    ...actual,
    doConversation: vi.fn(),
    conversationSelector: vi.fn((state) => state.conversation),
  };
});

vi.mock('../components/Notification/notify.ts', () => ({
  notify: vi.fn(),
  NotificationSeverity: {
    WARNING: 'warning',
  },
}));

describe('Textarea Component test suite', () => {
  const mockDispatch = vi.fn();
  let store: ReturnType<typeof configureStore>;

  const renderComponent = (initialState = {}) => {
    store = configureStore({
      reducer: {
        conversation: conversationReducer,
      },
      preloadedState: {
        conversation: {
          conversations: [],
          selectedConversationId: '',
          isGenerating: false,
          onGoingResult: '',
          files: [],
          links: [],
          ...initialState,
        },
      },
    });

    return render(
      <Provider store={store}>
        <I18nextProvider i18n={i18n}>
          <Textarea rows={1} setModelName={vi.fn()} />
        </I18nextProvider>
      </Provider>,
    );
  };

  beforeEach(() => {
    vi.mocked(useDispatch).mockReturnValue(mockDispatch);
    vi.mocked(useSelector).mockImplementation((selector) =>
      selector(store.getState()),
    );
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should render the component correctly', () => {
    renderComponent();

    expect(screen.getByTestId('textarea-intro')).toBeInTheDocument();
    expect(screen.getByTestId('textarea-wrapper')).toBeInTheDocument();
  });

  it('should not submit on Enter with empty message', () => {
    renderComponent();

    const textarea = screen.getByTestId('prompt-textarea');
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    expect(mockDispatch).not.toHaveBeenCalled();
  });

  it('should call handleSubmit when Enter is pressed without shift', () => {
    renderComponent();

    const textarea = screen.getByTestId('prompt-textarea');
    fireEvent.change(textarea, { target: { value: 'Hello' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    expect(textarea).toHaveValue('');
  });

  it('should clear the message on form submit', () => {
    renderComponent();

    const textarea = screen.getByTestId('prompt-textarea');
    fireEvent.change(textarea, { target: { value: 'Hello' } });

    const button = screen.getByTestId('submit-prompt');
    fireEvent.click(button);

    expect(textarea).toHaveValue('');
  });

  it('should submit the form and clear the message when Enter key is pressed without Shift key', () => {
    renderComponent();

    const textarea = screen.getByTestId('prompt-textarea');
    fireEvent.change(textarea, { target: { value: 'Hello' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    expect(textarea).toHaveValue('');
  });

  it('should not submit the form when Enter key is pressed with Shift key', () => {
    renderComponent();

    const textarea = screen.getByTestId('prompt-textarea');
    fireEvent.change(textarea, { target: { value: 'Hello' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });

    expect(mockDispatch).not.toHaveBeenCalled();
  });

  it('should notify when Enter key is pressed while generating', () => {
    renderComponent({ isGenerating: true });

    const textarea = screen.getByTestId('prompt-textarea');
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    expect(notify).toHaveBeenCalledWith(
      expect.any(String),
      NotificationSeverity.WARNING,
    );
    expect(mockDispatch).not.toHaveBeenCalled();
  });

  it('should not dispatch doConversation if message is empty on form submit', () => {
    renderComponent();

    const button = screen.getByTestId('submit-prompt');
    fireEvent.click(button);

    expect(mockDispatch).not.toHaveBeenCalled();
  });

  it('should not dispatch doConversation if message is empty when Enter key is pressed', () => {
    renderComponent();

    const textarea = screen.getByTestId('prompt-textarea');
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    expect(mockDispatch).not.toHaveBeenCalled();
  });
});
