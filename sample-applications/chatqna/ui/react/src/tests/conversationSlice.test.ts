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
  uploadFile,
  submitDataSourceURL,
  fetchInitialFiles,
  fetchInitialLinks,
  removeFile,
  removeAllFiles,
  removeLink,
  removeAllLinks,
} from '../redux/conversation/conversationSlice.ts';
import {
  ConversationReducer,
  File as CustomFile,
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
    links: [],
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
    const files: CustomFile[] = [
      { file_name: 'file1.txt', bucket_name: 'bucket' },
    ];
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

  it('should handle fetchInitialLinks.fulfilled', () => {
    const links: string[] = ['https://www.google.com'];
    const response = { data: links, status: 200 };
    const actual = conversationReducer(
      initialState,
      fetchInitialLinks.fulfilled(response, ''),
    );
    expect(actual.links).toEqual(links);
  });

  it('should handle fetchInitialLinks.pending', () => {
    const actual = conversationReducer(
      initialState,
      fetchInitialLinks.pending('', undefined),
    );
    expect(actual.isGenerating).toEqual(false);
  });

  it('should handle fetchInitialLinks.rejected', () => {
    const actual = conversationReducer(
      initialState,
      fetchInitialLinks.rejected(
        new Error('Failed to fetch links'),
        '',
        undefined,
      ),
    );
    expect(actual.links).toEqual([]);
  });

  it('should handle removeFile.fulfilled', () => {
    const stateWithFiles = {
      ...initialState,
      files: [{ file_name: 'file1.txt', bucket_name: 'bucket' }],
    };
    const actual = conversationReducer(
      stateWithFiles,
      removeFile.fulfilled(
        {
          status: 200,
          message: 'File deleted successfully',
          fileName: 'file1.txt',
        },
        '',
        {
          fileName: 'file1.txt',
          bucketName: 'bucket',
        },
      ),
    );
    expect(actual.files).toHaveLength(0);
  });

  it('should handle removeFile.rejected', () => {
    const stateWithFiles = {
      ...initialState,
      files: [{ file_name: 'file1.txt', bucket_name: 'bucket' }],
    };
    const actual = conversationReducer(
      stateWithFiles,
      removeFile.rejected(new Error('Failed to delete file'), '', {
        fileName: 'file1.txt',
        bucketName: 'bucket',
      }),
    );
    expect(actual.files).toHaveLength(1);
  });

  it('should handle removeLink.fulfilled', () => {
    const stateWithLinks = {
      ...initialState,
      links: ['https://www.google.com'],
    };
    const actual = conversationReducer(
      stateWithLinks,
      removeLink.fulfilled(
        {
          status: 200,
          message: 'Link deleted successfully',
          linkName: 'https://www.google.com',
        },
        '',
        {
          linkName: 'https://www.google.com',
        },
      ),
    );
    expect(actual.links).toHaveLength(0);
  });

  it('should handle removeLink.rejected', () => {
    const stateWithLinks = {
      ...initialState,
      links: ['https://www.google.com'],
    };
    const actual = conversationReducer(
      stateWithLinks,
      removeLink.rejected(new Error('Failed to delete link'), '', {
        linkName: 'https://www.google.com',
      }),
    );
    expect(actual.links).toHaveLength(1);
  });

  it('should handle removeAllFiles.fulfilled', () => {
    const files: CustomFile[] = [];
    const actual = conversationReducer(
      initialState,
      removeAllFiles.fulfilled({ status: 200, files }, '', {
        bucketName: 'bucket',
      }),
    );
    expect(actual.files).toEqual(files);
  });

  it('should handle removeAllFiles.rejected', () => {
    const actual = conversationReducer(
      initialState,
      removeAllFiles.rejected(new Error('Failed to delete all files'), '', {
        bucketName: 'bucket',
      }),
    );
    expect(actual.files).toEqual([]);
  });

  it('should handle removeAllLinks.fulfilled', () => {
    const links: string[] = [];
    const actual = conversationReducer(
      initialState,
      removeAllLinks.fulfilled({ status: 200, links }, '', {
        deleteAll: true,
      }),
    );
    expect(actual.links).toEqual(links);
  });

  it('should handle removeAllLinks.rejected', () => {
    const actual = conversationReducer(
      initialState,
      removeAllLinks.rejected(new Error('Failed to delete all links'), '', {
        deleteAll: true,
      }),
    );
    expect(actual.links).toEqual([]);
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
      files: [{ file_name: 'file1.txt', bucket_name: 'bucket' }],
    };
    const actual = conversationReducer(
      stateWithFiles,
      uploadFile.fulfilled(
        {
          data: { file_name: 'file2.txt', bucket_name: 'bucket' },
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
      files: [{ file_name: 'file1.txt', bucket_name: 'bucket' }],
    };
    const actual = conversationReducer(
      stateWithFiles,
      uploadFile.rejected(new Error('Failed to upload file'), '', {
        file: new File(['content'], 'file2.txt'),
      }),
    );
    expect(actual.files).toHaveLength(1);
  });

  it('should handle submitDataSourceURL.fulfilled', () => {
    const links: string[] = ['https://www.example.com'];
    const response = { data: links, status: 200 };
    const actual = conversationReducer(
      initialState,
      submitDataSourceURL.fulfilled(response, '', { link_list: links }),
    );
    expect(actual.links).toEqual(links);
  });

  it('should handle submitDataSourceURL.rejected', () => {
    const actual = conversationReducer(
      initialState,
      submitDataSourceURL.rejected(new Error('Failed to submit URL'), '', {
        link_list: ['https://www.example.com'],
      }),
    );
    expect(actual.links).toEqual([]);
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
