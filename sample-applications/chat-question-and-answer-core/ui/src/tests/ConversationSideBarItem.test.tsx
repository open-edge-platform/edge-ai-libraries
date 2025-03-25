// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { Provider, useDispatch } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { I18nextProvider } from 'react-i18next';

import ConversationSideBarItem from '../components/Conversation/ConversationSideBarItem.tsx';
import conversationReducer, {
  deleteConversation,
  updateConversationTitle,
} from '../redux/conversation/conversationSlice.ts';
import {
  notify,
  NotificationSeverity,
} from '../components/Notification/notify.ts';
import i18n from '../utils/i18n';

vi.mock('react-redux', async () => {
  const actual = await vi.importActual('react-redux');
  return {
    ...actual,
    useDispatch: vi.fn(),
  };
});

vi.mock('../components/Notification/notify.ts', () => ({
  notify: vi.fn(),
  NotificationSeverity: {
    WARNING: 'warning',
  },
}));

vi.mock('../redux/conversation/conversationSlice.ts', async () => {
  const actual = await vi.importActual(
    '../redux/conversation/conversationSlice.ts',
  );
  return {
    ...actual,
    deleteConversation: vi.fn(),
    updateConversationTitle: vi.fn(),
  };
});

describe('ConversationSideBarItem Component test suite', () => {
  const mockDispatch = vi.fn();
  const mockNotify = vi.mocked(notify);
  const mockDeleteConversation = vi.mocked(deleteConversation);
  const mockedUpdateConversationTitle = vi.mocked(updateConversationTitle);
  let store: ReturnType<typeof configureStore>;

  const renderComponent = (props = {}) => {
    return render(
      <Provider store={store}>
        <I18nextProvider i18n={i18n}>
          <ConversationSideBarItem
            title='Test Conversation'
            index='1'
            isActive={true}
            onClick={vi.fn()}
            {...props}
          />
        </I18nextProvider>
      </Provider>,
    );
  };

  beforeEach(() => {
    store = configureStore({
      reducer: {
        conversation: conversationReducer,
      },
    });

    renderComponent();
    vi.mocked(useDispatch).mockReturnValue(mockDispatch);
  });

  it('should render the component correctly', () => {
    expect(
      screen.getByTestId('conversation-sidebar-wrapper'),
    ).toBeInTheDocument();
    expect(screen.getByText('Test Conversation')).toBeInTheDocument();
  });

  it('should show edit and delete buttons when a conversation is selected', () => {
    const item = screen.getByText('Test Conversation');
    fireEvent.click(item);

    expect(screen.getByTestId('edit-conversation-button')).toBeInTheDocument();
    expect(
      screen.getByTestId('delete-conversation-button'),
    ).toBeInTheDocument();
  });

  it('should handle the click event to edit the conversation title', () => {
    const item = screen.getByText('Test Conversation');
    fireEvent.click(item);

    const editButton = screen.getByTestId('edit-conversation-button');
    fireEvent.click(editButton);
    expect(screen.getByDisplayValue('Test Conversation')).toBeInTheDocument();
  });

  it('should handle the click event to delete the conversation', () => {
    const item = screen.getByText('Test Conversation');
    fireEvent.click(item);

    const deleteButton = screen.getByTestId('delete-conversation-button');
    fireEvent.click(deleteButton);
    expect(screen.getByTestId('popup-modal')).toBeInTheDocument();
  });

  it('should handle the confirm delete action', async () => {
    const item = screen.getByText('Test Conversation');
    fireEvent.click(item);

    const deleteButton = screen.getByTestId('delete-conversation-button');
    fireEvent.click(deleteButton);

    const confirmButton = screen.getByRole('button', {
      name: new RegExp(i18n.t('delete'), 'i'),
    });
    fireEvent.click(confirmButton);

    expect(mockDeleteConversation).toHaveBeenCalledWith('1');
  });

  it('should handle the cancel delete action', () => {
    const item = screen.getByText('Test Conversation');
    fireEvent.click(item);

    const deleteButton = screen.getByTestId('delete-conversation-button');
    fireEvent.click(deleteButton);

    const closeButton = screen.getByRole('button', {
      name: new RegExp(i18n.t('cancel'), 'i'),
    });
    fireEvent.click(closeButton);

    expect(screen.queryByTestId('popup-modal')).not.toBeInTheDocument();
  });

  it('should handle the input change and blur events', () => {
    const item = screen.getByText('Test Conversation');
    fireEvent.click(item);

    const editButton = screen.getByTestId('edit-conversation-button');
    fireEvent.click(editButton);

    const input = screen.getByDisplayValue('Test Conversation');
    fireEvent.change(input, { target: { value: 'New Title' } });
    fireEvent.blur(input);

    expect(screen.getByText('Test Conversation')).toBeInTheDocument();
  });

  it('should handle the input key down event to update the conversation title', () => {
    const item = screen.getByText('Test Conversation');
    fireEvent.click(item);

    const editButton = screen.getByTestId('edit-conversation-button');
    fireEvent.click(editButton);

    const input = screen.getByDisplayValue('Test Conversation');
    fireEvent.change(input, { target: { value: 'New Title' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(mockedUpdateConversationTitle).toHaveBeenCalledWith({
      id: '1',
      updatedTitle: 'New Title',
    });
  });

  it('should notify when input is empty on pressing the Enter key', () => {
    const item = screen.getByText('Test Conversation');
    fireEvent.click(item);

    const editButton = screen.getByTestId('edit-conversation-button');
    fireEvent.click(editButton);

    const input = screen.getByDisplayValue('Test Conversation');
    fireEvent.change(input, { target: { value: '' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(mockNotify).toHaveBeenCalledWith(
      i18n.t('nonEmptyConversationTitle'),
      NotificationSeverity.WARNING,
    );
  });

  it('should handle the input blur event to reset the title', () => {
    const item = screen.getByText('Test Conversation');
    fireEvent.click(item);

    const editButton = screen.getByTestId('edit-conversation-button');
    fireEvent.click(editButton);

    const input = screen.getByDisplayValue('Test Conversation');
    fireEvent.change(input, { target: { value: 'New Title' } });
    fireEvent.blur(input);
    expect(screen.getByText('Test Conversation')).toBeInTheDocument();
  });
});
