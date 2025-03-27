// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { render, screen, fireEvent } from '@testing-library/react';
import { it, describe, expect, afterEach, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import { Provider, useDispatch } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';

import i18n from '../utils/i18n';
import conversationReducer, {
  setSelectedConversationId,
} from '../redux/conversation/conversationSlice.ts';
import ConversationSideBar from '../components/Conversation/ConversationSideBar.tsx';

vi.mock('react-redux', async () => {
  const actual = await vi.importActual('react-redux');
  return {
    ...actual,
    useDispatch: vi.fn(),
  };
});

vi.mock('../redux/conversation/conversationSlice.ts', async () => {
  const actual = await vi.importActual(
    '../redux/conversation/conversationSlice.ts',
  );
  return {
    ...actual,
    setSelectedConversationId: vi.fn(),
    conversationSelector: vi.fn((state) => state.conversation),
  };
});

describe('ConversationSideBar Component test suite', () => {
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
          ...initialState,
        },
      },
    });

    return render(
      <Provider store={store}>
        <I18nextProvider i18n={i18n}>
          <ConversationSideBar />
        </I18nextProvider>
      </Provider>,
    );
  };

  beforeEach(() => {
    vi.mocked(useDispatch).mockReturnValue(mockDispatch);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should render the component correctly', () => {
    renderComponent();

    expect(
      screen.getByTestId('conversation-sidebar-wrapper'),
    ).toBeInTheDocument();
  });

  it('should display chat history when there are conversations', () => {
    const initialState = {
      conversations: [
        { conversationId: '1', title: 'Conversation 1' },
        { conversationId: '2', title: 'Conversation 2' },
      ],
    };
    renderComponent(initialState);

    expect(screen.getByText(i18n.t('chatHistory'))).toBeInTheDocument();
    expect(screen.getByText('Conversation 1')).toBeInTheDocument();
    expect(screen.getByText('Conversation 2')).toBeInTheDocument();
  });

  it('should not display chat history when there are no conversations', () => {
    renderComponent();

    expect(screen.queryByText(i18n.t('chatHistory'))).not.toBeInTheDocument();
  });

  it('should disable sidebar when isGenerating is true', () => {
    const initialState = {
      isGenerating: true,
    };
    renderComponent(initialState);

    const sidebar = screen.getByTestId('conversation-sidebar-wrapper');
    expect(sidebar).toHaveStyle('pointer-events: none');
    expect(sidebar).toHaveStyle('opacity: 0.5');
  });

  it('should enable sidebar when isGenerating is false', () => {
    const initialState = {
      isGenerating: false,
    };
    renderComponent(initialState);

    const sidebar = screen.getByTestId('conversation-sidebar-wrapper');
    expect(sidebar).toHaveStyle('pointer-events: auto');
    expect(sidebar).toHaveStyle('opacity: 1');
  });

  it('should dispatch setSelectedConversationId when a conversation is clicked', () => {
    const initialState = {
      conversations: [
        { conversationId: '1', title: 'Conversation 1' },
        { conversationId: '2', title: 'Conversation 2' },
      ],
    };
    renderComponent(initialState);

    const conversationItem = screen.getByText('Conversation 1');
    fireEvent.click(conversationItem);

    expect(mockDispatch).toHaveBeenCalledWith(setSelectedConversationId('1'));
  });
});
