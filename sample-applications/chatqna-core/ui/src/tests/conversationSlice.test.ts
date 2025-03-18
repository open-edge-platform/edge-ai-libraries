// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { configureStore } from '@reduxjs/toolkit';
import { it, expect, describe, vi, afterEach, beforeEach } from 'vitest';
import { waitFor } from '@testing-library/react';

import conversationReducer, {
  logout,
  setOnGoingResult,
  setIsGenerating,
  addMessageToMessages,
  newConversation,
  deleteConversation,
  updateConversationTitle,
  createNewConversation,
  setSelectedConversationId,
  fetchInitialFiles,
  removeFile,
  removeAllFiles,
  uploadFile,
} from '../redux/conversation/conversationSlice.ts';
import {
  ConversationReducer,
  Message,
  MessageRole,
} from '../redux/conversation/conversation.ts';
import {
  getCurrentTimeStamp,
  removeLastTagIfPresent,
  uuidv4,
} from '../utils/util.ts';

vi.mock('../utils/util.ts', () => ({
  uuidv4: vi.fn(),
  getCurrentTimeStamp: vi.fn(),
  removeLastTagIfPresent: vi.fn(),
}));

const userPrompt: Message = {
  role: MessageRole.User,
  content: 'Hello',
  time: 100,
  conversationId: '',
};

const conversationRequest = {
  conversationId: 'test-uuid',
  userPrompt,
  messages: [],
  model: 'Intel/neural-chat-7b-v3-3',
};

interface RootTestState {
  conversation: ConversationReducer;
}

describe('conversationSlice test suite', () => {
  const initialState: ConversationReducer = {
    conversations: [],
    selectedConversationId: '',
    onGoingResult: '',
    files: [],
    isGenerating: false,
  };

  let store: ReturnType<typeof configureStore>;

  beforeEach(() => {
    store = configureStore({
      reducer: { conversation: conversationReducer },
      preloadedState: { conversation: initialState },
    });

    vi.mocked(uuidv4).mockReturnValue('test-uuid');
    vi.mocked(getCurrentTimeStamp).mockReturnValue(100);
    vi.mocked(removeLastTagIfPresent).mockImplementation((str) => str);
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it('should return the initial state', () => {
    expect(conversationReducer(undefined, { type: 'unknown' })).toEqual(
      initialState,
    );
  });

  it('should handle logout', () => {
    const actual = conversationReducer(initialState, logout());
    expect(actual).toEqual(initialState);
  });

  it('should handle setOnGoingResult', () => {
    const actual = conversationReducer(
      initialState,
      setOnGoingResult('result'),
    );
    expect(actual.onGoingResult).toEqual('result');
  });

  it('should handle setIsGenerating', () => {
    const actual = conversationReducer(initialState, setIsGenerating(true));
    expect(actual.isGenerating).toEqual(true);
  });

  it('should handle addMessageToMessages', () => {
    const message: Message = {
      role: MessageRole.User,
      content: 'Hello',
      time: 100,
      conversationId: 'test-uuid',
    };
    const stateWithConversation = {
      ...initialState,
      conversations: [
        {
          conversationId: 'test-uuid',
          title: 'Test Conversation',
          messages: [],
          responseStatus: false,
        },
      ],
      selectedConversationId: 'test-uuid',
    };
    const actual = conversationReducer(
      stateWithConversation,
      addMessageToMessages(message),
    );
    expect(actual.conversations[0].messages).toContainEqual(message);
  });

  it('should handle newConversation', () => {
    const actual = conversationReducer(initialState, newConversation());
    expect(actual.selectedConversationId).toEqual('');
    expect(actual.onGoingResult).toEqual('');
  });

  it('should handle deleteConversation', () => {
    const stateWithConversation = {
      ...initialState,
      conversations: [
        {
          conversationId: 'test-uuid',
          title: 'Test Conversation',
          messages: [],
          responseStatus: false,
        },
      ],
      selectedConversationId: 'test-uuid',
    };
    const actual = conversationReducer(
      stateWithConversation,
      deleteConversation('test-uuid'),
    );
    expect(actual.conversations).toHaveLength(0);
    expect(actual.selectedConversationId).toEqual('');
  });

  it('should handle updateConversationTitle', () => {
    const stateWithConversation = {
      ...initialState,
      conversations: [
        {
          conversationId: 'test-uuid',
          title: 'Old Title',
          messages: [],
          responseStatus: false,
        },
      ],
    };
    const actual = conversationReducer(
      stateWithConversation,
      updateConversationTitle({ id: 'test-uuid', updatedTitle: 'New Title' }),
    );
    expect(actual.conversations[0].title).toEqual('New Title');
  });

  it('should handle createNewConversation', () => {
    const message: Message = {
      role: MessageRole.User,
      content: 'Hello',
      time: 100,
      conversationId: 'test-uuid',
    };
    const actual = conversationReducer(
      initialState,
      createNewConversation({
        title: 'New Conversation',
        id: 'test-uuid',
        message,
      }),
    );
    expect(actual.conversations).toHaveLength(1);
    expect(actual.conversations[0].title).toEqual('New Conversation');
    expect(actual.conversations[0].messages).toContainEqual(message);
  });

  it('should handle setSelectedConversationId', () => {
    const actual = conversationReducer(
      initialState,
      setSelectedConversationId('test-uuid'),
    );
    expect(actual.selectedConversationId).toEqual('test-uuid');
  });

  it('should handle fetchInitialFiles.fulfilled', () => {
    const files = ['file1.txt'];
    const response = { data: files, status: 200 };
    const actual = conversationReducer(
      initialState,
      fetchInitialFiles.fulfilled(response, ''),
    );
    expect(actual.files).toEqual(files);
  });

  it('should handle fetchInitialFiles.pending', () => {
    const actual = conversationReducer(
      initialState,
      fetchInitialFiles.pending('', undefined),
    );
    expect(actual.isGenerating).toEqual(false);
  });

  it('should handle fetchInitialFiles.rejected', () => {
    const actual = conversationReducer(
      initialState,
      fetchInitialFiles.rejected(
        new Error('Failed to fetch files'),
        '',
        undefined,
      ),
    );
    expect(actual.files).toEqual([]);
  });

  it('should handle removeFile.fulfilled', () => {
    const stateWithFiles = {
      ...initialState,
      files: ['file1.txt'],
    };
    const actual = conversationReducer(
      stateWithFiles,
      removeFile.fulfilled('file1.txt', '', { fileName: 'file1.txt' }),
    );
    expect(actual.files).toHaveLength(0);
  });

  it('should handle removeFile.rejected', () => {
    const stateWithFiles = {
      ...initialState,
      files: ['file1.txt'],
    };
    const actual = conversationReducer(
      stateWithFiles,
      removeFile.rejected(new Error('Failed to delete file'), '', {
        fileName: 'file1.txt',
      }),
    );
    expect(actual.files).toHaveLength(1);
  });

  it('should handle removeAllFiles.fulfilled', () => {
    const stateWithFiles = {
      ...initialState,
      files: ['file1.txt', 'file2.txt'],
    };
    const actual = conversationReducer(
      stateWithFiles,
      removeAllFiles.fulfilled([], ''),
    );
    expect(actual.files).toEqual([]);
  });

  it('should handle removeAllFiles.rejected', () => {
    const actual = conversationReducer(
      initialState,
      removeAllFiles.rejected(new Error('Failed to delete all files'), ''),
    );
    expect(actual.files).toEqual([]);
  });

  it('should handle doConversation for new conversation', async () => {
    const mockDoConversation = vi.fn();
    mockDoConversation.mockImplementation(() => {
      store.dispatch(
        createNewConversation({
          title: userPrompt.content,
          id: 'test-uuid',
          message: userPrompt,
        }),
      );
      store.dispatch(setSelectedConversationId('test-uuid'));
    });

    await mockDoConversation(conversationRequest);

    await waitFor(() => {
      const state = store.getState() as RootTestState;
      expect(state.conversation.conversations).toHaveLength(1);
      expect(state.conversation.selectedConversationId).toEqual('test-uuid');
    });
  });

  it('should handle doConversation for existing conversation', async () => {
    const stateWithConversation = {
      ...initialState,
      conversations: [
        {
          conversationId: 'test-uuid',
          title: 'Test Conversation',
          messages: [],
          responseStatus: false,
        },
      ],
      selectedConversationId: 'test-uuid',
    };

    store = configureStore({
      reducer: {
        conversation: conversationReducer,
      },
      preloadedState: {
        conversation: stateWithConversation,
      },
    });

    const conversationRequest = {
      conversationId: 'test-uuid',
      userPrompt,
    };

    const mockDoConversation = vi.fn();
    mockDoConversation.mockImplementation(() => {
      store.dispatch(addMessageToMessages(userPrompt));
    });

    await mockDoConversation(conversationRequest);

    await waitFor(() => {
      const state = store.getState() as RootTestState;
      expect(state.conversation.conversations[0].messages).toContainEqual(
        userPrompt,
      );
    });
  });

  it('should handle uploadFile.fulfilled', () => {
    const stateWithFiles = {
      ...initialState,
      files: ['file1.txt'],
    };
    const actual = conversationReducer(
      stateWithFiles,
      uploadFile.fulfilled(
        {
          data: 'file2.txt',
          status: 200,
        },
        '',
        { file: new File(['content'], 'file2.txt') },
      ),
    );
    expect(actual.files).toHaveLength(1);
  });

  it('should handle uploadFile.rejected', () => {
    const stateWithFiles = {
      ...initialState,
      files: ['file1.txt'],
    };
    const actual = conversationReducer(
      stateWithFiles,
      uploadFile.rejected(new Error('Failed to upload file'), '', {
        file: new File(['content'], 'file2.txt'),
      }),
    );
    expect(actual.files).toHaveLength(1);
  });

  it('should handle doConversation error', async () => {
    const mockDoConversation = vi.fn();
    mockDoConversation.mockImplementation(() => {
      throw new Error('Failed to connect');
    });

    try {
      await mockDoConversation(conversationRequest);
    } catch (error) {
      if (error instanceof Error) {
        expect(error.message).toEqual('Failed to connect');
      }
    }

    await waitFor(() => {
      const state = store.getState() as RootTestState;
      expect(state.conversation.isGenerating).toEqual(false);
      expect(state.conversation.onGoingResult).toEqual('');
    });
  });
});
