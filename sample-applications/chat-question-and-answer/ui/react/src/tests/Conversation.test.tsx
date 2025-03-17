// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { Provider, useDispatch } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { I18nextProvider } from 'react-i18next';

import Conversation from '../components/Conversation/Conversation.tsx';
import conversationReducer, {
  fetchInitialFiles,
  fetchInitialLinks,
} from '../redux/conversation/conversationSlice.ts';
import i18n from '../utils/i18n';

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
    fetchInitialFiles: vi.fn(),
    fetchInitialLinks: vi.fn(),
    conversationSelector: vi.fn((state) => state.conversation),
  };
});

describe('Conversation Component test suite', () => {
  const mockDispatch = vi.fn();
  const mockFetchInitialFiles = vi.mocked(fetchInitialFiles);
  const mockFetchInitialLinks = vi.mocked(fetchInitialLinks);
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
          <Conversation />
        </I18nextProvider>
      </Provider>,
    );
  };

  beforeEach(() => {
    vi.mocked(useDispatch).mockReturnValue(mockDispatch);
    Element.prototype.scrollTo = vi.fn();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should render the component correctly', () => {
    renderComponent();

    expect(screen.getByTestId('conversation-container')).toBeInTheDocument();
  });

  it('should fetch initial files on mount', () => {
    renderComponent();

    expect(mockDispatch).toHaveBeenCalledWith(mockFetchInitialFiles());
  });

  it('should fetch initial links on mount', () => {
    renderComponent();

    expect(mockDispatch).toHaveBeenCalledWith(mockFetchInitialLinks());
  });

  it('should display Textarea if no selectedConversationId', () => {
    renderComponent();

    console.log(store.getState());

    expect(screen.getByTestId('textarea-intro')).toBeInTheDocument();
  });

  it('should display conversation title if selectedConversationId is present', () => {
    const initialState = {
      conversations: [
        {
          conversationId: '1',
          title: 'Test Conversation',
          messages: [],
          responseStatus: false,
        },
      ],
      selectedConversationId: '1',
    };
    renderComponent(initialState);

    expect(screen.getByText('Test Conversation')).toBeInTheDocument();
  });

  it('should display messages if selectedConversationId is present', () => {
    const initialState = {
      conversations: [
        {
          conversationId: '1',
          title: 'Test Conversation',
          messages: [
            { time: 1620000000, role: 'user', content: 'Hello' },
            { time: 1620000001, role: 'bot', content: 'Hi there!' },
          ],
        },
      ],
      selectedConversationId: '1',
    };
    renderComponent(initialState);

    expect(screen.getByText('Hello')).toBeInTheDocument();
    expect(screen.getByText('Hi there!')).toBeInTheDocument();
  });

  it('should display ongoing result if isGenerating is true', () => {
    const initialState = {
      conversations: [
        {
          conversationId: '1',
          title: 'Test Conversation',
          messages: [],
        },
      ],
      selectedConversationId: '1',
      isGenerating: true,
      onGoingResult: 'Generating...',
    };
    renderComponent(initialState);

    expect(screen.getByText('Generating...')).toBeInTheDocument();
  });
});
