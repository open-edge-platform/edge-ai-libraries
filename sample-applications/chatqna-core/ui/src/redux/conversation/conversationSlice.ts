// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { createSlice, PayloadAction, createAsyncThunk } from '@reduxjs/toolkit';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { createSelector } from 'reselect';

import {
  ConversationReducer,
  ConversationRequest,
  Message,
  MessageRole,
} from './conversation.ts';
import client from '../../utils/client.ts';
import { CHAT_QNA_URL, DATA_PREP_URL } from '../../config.ts';
import {
  checkHealth,
  getCurrentTimeStamp,
  getTitle,
  uuidv4,
} from '../../utils/util.ts';
import store, { RootState } from '../store.ts';
import { NotificationSeverity } from '../../components/Notification/notify.ts';
import { notify } from '../../components/Notification/notify.ts';

const initialState: ConversationReducer = {
  conversations: [],
  selectedConversationId: '',
  onGoingResult: '',
  files: [],
  isGenerating: false,
};

export const conversationSlice = createSlice({
  name: 'conversation',
  initialState,
  reducers: {
    logout: (state) => {
      state.conversations = [];
      state.selectedConversationId = '';
      state.onGoingResult = '';
      state.files = [];
    },

    setOnGoingResult: (state, action: PayloadAction<string>) => {
      state.onGoingResult = action.payload;
    },

    setIsGenerating: (state, action: PayloadAction<boolean>) => {
      state.isGenerating = action.payload;
    },

    addMessageToMessages: (state, action: PayloadAction<Message>) => {
      const selectedConversation = state.conversations.find(
        (conversation) =>
          conversation.conversationId === state.selectedConversationId,
      );
      selectedConversation?.messages?.push(action.payload);
    },

    newConversation: (state) => {
      state.selectedConversationId = '';
      state.onGoingResult = '';
    },

    deleteConversation: (state, action: PayloadAction<string>) => {
      const conversationIndex = state.conversations.findIndex(
        (conversation) => conversation.conversationId === action.payload,
      );
      if (conversationIndex !== -1) {
        state.conversations.splice(conversationIndex, 1);
        if (state.selectedConversationId === action.payload) {
          state.selectedConversationId = '';
        }
        if (state.conversations.length === 0) {
          state.selectedConversationId = '';
        }
      }
    },

    updateConversationTitle: (
      state,
      action: PayloadAction<{ id: string; updatedTitle: string }>,
    ) => {
      const selectedConversation = state.conversations.find(
        (conversation) => conversation.conversationId === action.payload.id,
      );
      if (selectedConversation)
        selectedConversation.title = action.payload.updatedTitle;
    },

    createNewConversation: (
      state,
      action: PayloadAction<{ title: string; id: string; message: Message }>,
    ) => {
      state.conversations.unshift({
        title: action.payload.title,
        conversationId: action.payload.id,
        messages: [action.payload.message],
        responseStatus: false,
      });
    },

    setSelectedConversationId: (state, action: PayloadAction<string>) => {
      state.selectedConversationId = action.payload;
    },

    setResponseStatus: (state, action: PayloadAction<boolean>) => {
      const selectedConversation = state.conversations.find(
        (conversation) =>
          conversation.conversationId === state.selectedConversationId,
      );
      if (selectedConversation) {
        selectedConversation.responseStatus = action.payload;
      }
    },
  },
  extraReducers: (builder) => {
    builder.addCase(fetchInitialFiles.fulfilled, (state, action) => {
      state.files = action.payload.data;
    });
    builder.addCase(fetchInitialFiles.rejected, (state) => {
      state.files = [];
      state.conversations = [];
      state.selectedConversationId = '';
    });
    builder.addCase(uploadFile.fulfilled, () => {});
    builder.addCase(uploadFile.rejected, () => {});
    builder.addCase(removeFile.fulfilled, (state, action) => {
      const index = state.files.findIndex((file) => file === action.payload);
      if (index !== -1) {
        state.files.splice(index, 1);
      }
    });
    builder.addCase(removeFile.rejected, () => {});
    builder.addCase(removeAllFiles.fulfilled, (state, action) => {
      state.files = action.payload;
    });
    builder.addCase(removeAllFiles.rejected, () => {});
  },
});

export const fetchInitialFiles = createAsyncThunk(
  'conversation/fetchInitialFiles',
  async (_, { rejectWithValue }) => {
    try {
      const response = await client.get(DATA_PREP_URL);
      if (response.status === 200) {
        const validFiles: string[] = response.data.metadata.documents;
        return { data: validFiles, status: response.status };
      } else {
        throw new Error(`Request failed with status code ${response.status}`);
      }
    } catch (error) {
      if (client.isAxiosError(error) && error.response) {
        return rejectWithValue({
          status: error.status,
          message: error.message || 'Failed to fetch files',
        });
      } else {
        return rejectWithValue({
          status: 500,
          message: (error as Error).message || 'An unknown error occured',
        });
      }
    }
  },
);

export const uploadFile = createAsyncThunk(
  'conversation/uploadFile',
  async ({ file }: { file: File }, { rejectWithValue }) => {
    try {
      const body = new FormData();
      body.append('files', file);

      const response = await client.post(DATA_PREP_URL, body);

      if (response.status === 200) {
        return { data: response.data, status: response.status };
      } else {
        throw new Error(`Request failed with status code ${response.status}`);
      }
    } catch (error) {
      if (client.isAxiosError(error) && error.response) {
        return rejectWithValue({
          status: error.status,
          message: error.message || 'Failed to upload the file',
        });
      } else {
        return rejectWithValue({
          status: 500,
          message: (error as Error).message || 'An unknown error occured',
        });
      }
    }
  },
);

export const removeFile = createAsyncThunk(
  'conversation/removeFile',
  async (
    { fileName, deleteAll = false }: { fileName: string; deleteAll?: boolean },
    { getState, rejectWithValue },
  ) => {
    try {
      const state = getState() as RootState;
      const file = state.conversations.files.find((file) => file === fileName);

      if (!file) {
        throw new Error('File not found');
      }

      const response = await client.delete(
        `${DATA_PREP_URL}?document=${encodeURIComponent(fileName)}&delete_all=${deleteAll}`,
      );

      if (response.status === 204) {
        return fileName;
      } else {
        throw new Error(`Request failed with status code ${response.status}`);
      }
    } catch (error) {
      if (client.isAxiosError(error) && error.response) {
        return rejectWithValue({
          status: error.status,
          message: error.message || 'Failed to delete the file',
        });
      } else {
        return rejectWithValue({
          status: 500,
          message: (error as Error).message || 'An unknown error occurred',
        });
      }
    }
  },
);

export const removeAllFiles = createAsyncThunk(
  'conversation/removeAllFiles',
  async (_, { getState, rejectWithValue }) => {
    try {
      const state = getState() as RootState;

      if (state.conversations.files.length === 0) {
        throw new Error('No files to delete');
      }

      const response = await client.delete(
        `${DATA_PREP_URL}?delete_all=${true}`,
      );
      if (response.status === 204) {
        return [];
      } else {
        throw new Error(`Request failed with status code ${response.status}`);
      }
    } catch (error) {
      if (client.isAxiosError(error) && error.response) {
        return rejectWithValue({
          status: error.status,
          message: error.message || 'Failed to delete the file(s)',
        });
      } else {
        return rejectWithValue({
          status: 500,
          message: (error as Error).message || 'An unknown error occurred',
        });
      }
    }
  },
);

export const doConversation = (conversationRequest: ConversationRequest) => {
  const { userPrompt } = conversationRequest;
  const { conversationId } = userPrompt;

  const body = {
    input: userPrompt.content,
    stream: true,
  };

  store.dispatch(setIsGenerating(true));
  store.dispatch(setResponseStatus(false));

  if (!conversationId) {
    // New Conversation
    const id = uuidv4();
    store.dispatch(
      createNewConversation({
        title: getTitle(userPrompt.content),
        id,
        message: userPrompt,
      }),
    );
    store.dispatch(setSelectedConversationId(id));
  } else {
    store.dispatch(addMessageToMessages(userPrompt));
  }

  let result: string = '';
  try {
    fetchEventSource(CHAT_QNA_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      openWhenHidden: true,
      async onopen(response) {
        if (response.ok) {
          return;
        } else if (
          response.status >= 400 &&
          response.status < 500 &&
          response.status !== 429
        ) {
          const e = await response.json();
          console.log(e);
          throw Error(e.error.message);
        } else {
          console.log('error', response);
        }
      },
      onmessage(msg) {
        if (msg?.data !== '[DONE]') {
          try {
            if (msg.data) {
              result += msg.data;
              if (result) {
                store.dispatch(setOnGoingResult(result));
              }
            }
          } catch (e) {
            console.error('Error parsing message:', e);
          }
        }
      },
      onerror(err) {
        console.log('error', err);
        store.dispatch(setIsGenerating(false));
        store.dispatch(setOnGoingResult(''));

        (async () => {
          const healthStatus = await checkHealth();
          if (healthStatus.status !== 200) {
            notify(
              healthStatus.message ||
                'LLM model server is not ready to accept connections. Please try after a few minutes.',
              NotificationSeverity.ERROR,
            );
          } else {
            notify(
              err.message || 'Could not connect to backend at this moment',
              NotificationSeverity.ERROR,
            );
          }
        })();
        throw err;
      },
      onclose() {
        store.dispatch(setOnGoingResult(''));
        store.dispatch(setIsGenerating(false));
        store.dispatch(setResponseStatus(true));
        store.dispatch(
          addMessageToMessages({
            role: MessageRole.Assistant,
            content: result,
            time: getCurrentTimeStamp(),
            conversationId,
          }),
        );
      },
    });
  } catch (err) {
    console.log(err);
  }
};

export const {
  logout,
  setOnGoingResult,
  setIsGenerating,
  newConversation,
  deleteConversation,
  updateConversationTitle,
  addMessageToMessages,
  setSelectedConversationId,
  setResponseStatus,
  createNewConversation,
} = conversationSlice.actions;

const selectConversationState = (state: RootState) => state.conversations;

export const conversationSelector = createSelector(
  [selectConversationState],
  (conversationState) => ({
    files: conversationState?.files || [],
    conversations: conversationState?.conversations || [],
    selectedConversationId: conversationState?.selectedConversationId || '',
    onGoingResult: conversationState?.onGoingResult || '',
    isGenerating: conversationState?.isGenerating || false,
  }),
);

export default conversationSlice.reducer;
