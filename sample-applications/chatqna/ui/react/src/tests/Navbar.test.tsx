// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import { it, describe, expect, afterEach, vi, beforeEach } from 'vitest';
import { Provider, useDispatch } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';

import i18n from '../utils/i18n';
import conversationReducer from '../redux/conversation/conversationSlice.ts';
import Navbar from '../components/Navbar/Navbar.tsx';

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
    conversationSelector: vi.fn((state) => state.conversation),
  };
});

describe('Navbar Component test suite', () => {
  let store: ReturnType<typeof configureStore>;
  const mockDispatch = vi.fn();

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
          <Navbar />
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

    expect(screen.getByTestId('navbar-wrapper')).toBeInTheDocument();
  });

  it('should not render askQuestion button when selectedConversationId is not present', () => {
    renderComponent();

    expect(screen.queryByTestId('ask-question-button')).not.toBeInTheDocument();
  });

  it('should render askQuestion button when selectedConversationId is present', () => {
    const initialState = {
      selectedConversationId: '123',
      isGenerating: false,
    };
    renderComponent(initialState);

    expect(screen.getByTestId('ask-question-button')).toBeInTheDocument();
  });

  it('should call handleNewConversation when the askQuestion button is clicked', () => {
    const initialState = {
      selectedConversationId: '123',
      isGenerating: false,
    };
    renderComponent(initialState);

    const askQuestionButton = screen.getByTestId('ask-question-button');
    fireEvent.click(askQuestionButton);

    expect(
      screen.getByText(new RegExp(i18n.t('askQuestion'), 'i')),
    ).toBeInTheDocument();
  });

  it('should open the drawer when the manageContext button is clicked', () => {
    renderComponent();

    const manageContextButton = screen.getByTestId('manage-context-button');
    fireEvent.click(manageContextButton);

    expect(
      screen.getByText(new RegExp(i18n.t('contexts'), 'i')),
    ).toBeInTheDocument();
  });

  it('should disable buttons when isGenerating is true', () => {
    const initialState = {
      isGenerating: true,
      selectedConversationId: '123',
    };
    renderComponent(initialState);

    const askQuestionButton = screen.getByTestId('ask-question-button');
    const manageContextButton = screen.getByTestId('manage-context-button');

    expect(askQuestionButton).toBeDisabled();
    expect(manageContextButton).toBeDisabled();
  });
});
