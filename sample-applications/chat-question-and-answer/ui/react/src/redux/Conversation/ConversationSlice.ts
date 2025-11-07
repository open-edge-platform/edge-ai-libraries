// Copyright (C) 2024 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { PayloadAction, createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import { RootState } from "../store";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { Message, MessageRole, ConversationReducer, ConversationRequest, File } from "./Conversation";
import { getCurrentTimeStamp, uuidv4, checkHealth } from "../../utils/util";
import { createAsyncThunkWrapper } from "../thunkUtil";
import client from "../../utils/client";
import { notifications } from "@mantine/notifications";
import { CHAT_QNA_URL, DATA_PREP_URL, LINK_PREP_URL, MAX_TOKENS, MODEL_URL } from "../../config";


const initialState: ConversationReducer = {
  conversations: [],
  selectedConversationId: "",
  onGoingResults: {},
  modelName: "...",
  files: [],
  links: [],
  isGenerating: {},
  isWaitingForFirstToken: {},
  isUploading: false,
};

export const ConversationSlice = createSlice({
  name: "Conversation",
  initialState,
  reducers: {
    setOnGoingResultForConversation: (state, action: PayloadAction<{ conversationId: string; result: string }>) => {
      const { conversationId, result } = action.payload;
      state.onGoingResults[conversationId] = result;
    },
    clearOnGoingResultForConversation: (state, action: PayloadAction<string>) => {
      delete state.onGoingResults[action.payload];
    },
    addMessageToConversation: (state, action: PayloadAction<{ conversationId: string; message: Message }>) => {
      const { conversationId, message } = action.payload;
      const conversation = state.conversations.find((conv) => conv.conversationId === conversationId);
      conversation?.Messages?.push(message);
    },
    newConversation: (state) => {
      state.selectedConversationId = "";
      //allow multiple conversations to generate simultaneously by not clearing ongoing and generating state
    },
    createNewConversation: (state, action: PayloadAction<{ title: string; id: string; message: Message }>) => {
      state.conversations.push({
        title: action.payload.title,
        conversationId: action.payload.id,
        Messages: [action.payload.message],
      });
    },
    setSelectedConversationId: (state, action: PayloadAction<string>) => {
      state.selectedConversationId = action.payload;
    },
    deleteConversation: (state, action: PayloadAction<string>) => {
      const conversationId = action.payload;
      if (state.selectedConversationId === conversationId) {
        state.selectedConversationId = "";
      }
      // Clean up only the specific conversation's ongoing state
      delete state.onGoingResults[conversationId];
      delete state.isGenerating[conversationId];
      // Remove the conversation from the list
      state.conversations = state.conversations.filter(conv => conv.conversationId !== conversationId);
    },
    updateConversationTitle: (state, action: PayloadAction<{ id: string; updatedTitle: string }>) => {
      const { id, updatedTitle } = action.payload;
      const conversation = state.conversations.find(conv => conv.conversationId === id);
      if (conversation) {
        conversation.title = updatedTitle;
      }
    },
    setIsGenerating: (state, action: PayloadAction<{ conversationId: string; isGenerating: boolean }>) => {
      const { conversationId, isGenerating } = action.payload;
      if (isGenerating) {
        state.isGenerating[conversationId] = true;
      } else {
        delete state.isGenerating[conversationId];
      }
    },
    setIsWaitingForFirstToken: (state, action: PayloadAction<{ conversationId: string; isWaiting: boolean }>) => {
      const { conversationId, isWaiting } = action.payload;
      if (isWaiting) {
        state.isWaitingForFirstToken[conversationId] = true;
      } else {
        delete state.isWaitingForFirstToken[conversationId];
      }
    },
  },
  extraReducers(builder) {
    // File management
    builder.addCase(fetchInitialFiles.fulfilled, (state, action) => {
      state.files = action.payload.data;
    });
    builder.addCase(fetchInitialFiles.rejected, (state) => {
      state.files = [];
    });
    builder.addCase(uploadFile.pending, (state) => {
      state.isUploading = true;
    });
    builder.addCase(uploadFile.fulfilled, (state) => {
      state.isUploading = false;
      // Hide the loading notification first
      notifications.hide("upload-file");
      // Show a new success notification
      notifications.show({
        message: "File Uploaded Successfully",
        color: "green",
        autoClose: 3000,
      });
    });
    builder.addCase(uploadFile.rejected, (state) => {
      state.isUploading = false;
      // Hide the loading notification first
      notifications.hide("upload-file");
      // Show a new error notification
      notifications.show({
        color: "red",
        message: "Failed to Upload file",
        autoClose: 3000,
      });
    });
    builder.addCase(removeFile.fulfilled, (state, action) => {
      const index = state.files.findIndex(
        (file) => file.file_name === action.payload.fileName
      );
      if (index !== -1) {
        state.files.splice(index, 1);
      }
      notifications.show({
        message: "File deleted successfully",
        color: "green",
      });
    });
    builder.addCase(removeFile.rejected, () => {
      notifications.show({
        color: "red",
        message: "Failed to delete file",
      });
    });
    builder.addCase(removeAllFiles.fulfilled, (state) => {
      state.files = [];
      notifications.show({
        message: "All files deleted successfully",
        color: "green",
      });
    });
    builder.addCase(removeAllFiles.rejected, () => {
      notifications.show({
        color: "red",
        message: "Failed to delete all files",
      });
    });
    
    // Link management
    builder.addCase(fetchInitialLinks.fulfilled, (state, action) => {
      state.links = action.payload.data;
    });
    builder.addCase(fetchInitialLinks.rejected, (state) => {
      state.links = [];
    });
    builder.addCase(submitDataSourceURL.pending, (state) => {
      state.isUploading = true;
    });
    builder.addCase(submitDataSourceURL.fulfilled, (state) => {
      state.isUploading = false;
      // Hide the loading notification first
      notifications.hide("submit-url");
      // Show a new success notification
      notifications.show({
        message: "URLs submitted successfully",
        color: "green",
        autoClose: 3000,
      });
    });
    builder.addCase(submitDataSourceURL.rejected, (state) => {
      state.isUploading = false;
      // Hide the loading notification first
      notifications.hide("submit-url");
      // Show a new error notification
      notifications.show({
        message: "Failed to submit URLs",
        color: "red",
        autoClose: 3000,
      });
    });
    builder.addCase(removeLink.fulfilled, (state, action) => {
      const index = state.links.findIndex(
        (link) => link === action.payload.linkName
      );
      if (index !== -1) {
        state.links.splice(index, 1);
      }
      notifications.show({
        message: "Link deleted successfully",
        color: "green",
      });
    });
    builder.addCase(removeLink.rejected, () => {
      notifications.show({
        color: "red",
        message: "Failed to delete link",
      });
    });
    builder.addCase(removeAllLinks.fulfilled, (state) => {
      state.links = [];
      notifications.show({
        message: "All links deleted successfully",
        color: "green",
      });
    });
    builder.addCase(removeAllLinks.rejected, () => {
      notifications.show({
        color: "red",
        message: "Failed to delete all links",
      });
    });
    
    // Model name
    builder.addCase(fetchModelName.fulfilled, (state, action) => {
      state.modelName = action.payload;
    });
    builder.addCase(fetchModelName.rejected, (state) => {
      state.modelName = "Unknown Model";
    });
  },
});

export const fetchModelName = createAsyncThunkWrapper(
  "conversation/fetchModelName",
  async (_, {}) => {
    const response = await client.get(MODEL_URL);
    console.log("Fetched model name:", response);
    return response.data.llm_model || "Unknown Model";
  },
);

export const fetchInitialFiles = createAsyncThunk(
  'conversation/fetchInitialFiles',
  async (_, { rejectWithValue }) => {
    try {
      const response = await client.get(DATA_PREP_URL);
      if (response.status === 200) {
        const rawFiles: File[] = response.data;
        const validFiles: File[] = rawFiles.filter(
          (file) => file.file_name && file.bucket_name,
        );
        return { data: validFiles, status: response.status };
      } else {
        return rejectWithValue({
          message: response.data.message || 'Failed to fetch files',
          status: response.status,
        });
      }
    } catch (error: any) {
      return rejectWithValue({
        message: error.message || 'An unknown error occurred',
        status: 500,
      });
    }
  },
);

export const fetchInitialLinks = createAsyncThunk(
  'conversation/fetchInitialLinks',
  async (_, { rejectWithValue }) => {
    try {
      const response = await client.get(LINK_PREP_URL);
      if (response.status === 200) {
        return { data: response.data, status: response.status };
      } else {
        return rejectWithValue({
          message: response.data.message || 'Failed to fetch links',
          status: response.status,
        });
      }
    } catch (error: any) {
      return rejectWithValue({
        message: error.message || 'An unknown error occurred',
        status: 500,
      });
    }
  },
);

export const removeFile = createAsyncThunk(
  'conversation/removeFile',
  async (
    {
      fileName,
      bucketName,
      deleteAll = false,
    }: { fileName: string; bucketName: string; deleteAll?: boolean },
    { rejectWithValue },
  ) => {
    try {
      const response = await client.delete(
        `${DATA_PREP_URL}?bucket_name=${bucketName}&file_name=${encodeURIComponent(fileName)}&delete_all=${deleteAll}`,
      );

      if (response.status >= 200 && response.status <= 204) {
        return {
          status: response.status,
          message: response.statusText.toLowerCase(),
          fileName,
        };
      } else {
        return rejectWithValue({
          status: response.status,
          message: response.data.message || 'File deletion failed',
        });
      }
    } catch (error: any) {
      return rejectWithValue({
        status: 500,
        message: error.message || 'An unknown error occurred',
      });
    }
  },
);

export const removeAllFiles = createAsyncThunk(
  'conversation/removeAllFiles',
  async (
    {
      bucketName,
      deleteAll = true,
    }: { bucketName: string; deleteAll?: boolean },
    { rejectWithValue },
  ) => {
    try {
      const response = await client.delete(
        `${DATA_PREP_URL}?bucket_name=${bucketName}&delete_all=${deleteAll}`,
      );

      if (response.status >= 200 && response.status <= 204) {
        return { status: response.status, files: [] as File[] };
      } else {
        return rejectWithValue({
          status: response.status,
          message: response.data.message || 'Delete failed',
        });
      }
    } catch (error: any) {
      return rejectWithValue({
        status: 500,
        message: error.message || 'An unknown error occurred',
      });
    }
  },
);

export const removeLink = createAsyncThunk(
  'conversation/removeLink',
  async (
    { linkName, deleteAll = false }: { linkName: string; deleteAll?: boolean },
    { rejectWithValue },
  ) => {
    try {
      const response = await client.delete(
        `${LINK_PREP_URL}?url=${encodeURIComponent(linkName)}&delete_all=${deleteAll}`,
      );

      if (response.status >= 200 && response.status <= 204) {
        return {
          status: response.status,
          message: response.statusText.toLowerCase(),
          linkName,
        };
      } else {
        return rejectWithValue({
          status: response.status,
          message: response.data.message || 'Link deletion failed',
        });
      }
    } catch (error: any) {
      return rejectWithValue({
        status: 500,
        message: error.message || 'An unknown error occurred',
      });
    }
  },
);

export const removeAllLinks = createAsyncThunk(
  'conversation/removeAllLinks',
  async (
    { deleteAll = true }: { deleteAll?: boolean },
    { rejectWithValue },
  ) => {
    try {
      const response = await client.delete(
        `${LINK_PREP_URL}?delete_all=${deleteAll}`,
      );

      if (response.status >= 200 && response.status <= 204) {
        return { status: response.status, links: [] as string[] };
      } else {
        return rejectWithValue({
          status: response.status,
          message: response.data.message || 'Delete failed',
        });
      }
    } catch (error: any) {
      return rejectWithValue({
        status: 500,
        message: error.message || 'An unknown error occurred',
      });
    }
  },
);

export const submitDataSourceURL = createAsyncThunkWrapper(
  "conversation/submitDataSourceURL",
  async ({ link_list }: { link_list: string[] }, {}) => {
    notifications.show({
      id: "submit-url",
      message: "Submitting URLs...",
      loading: true,
    });
    const response = await client.post(LINK_PREP_URL, link_list);
    return response.data;
  },
);

export const uploadFile = createAsyncThunkWrapper("conversation/uploadFile", async ({ file }: { file: globalThis.File }, {}) => {
  const body = new FormData();
  body.append("files", file);

  notifications.show({
    id: "upload-file",
    message: "Uploading File...",
    loading: true,
  });
  const response = await client.post(DATA_PREP_URL, body);
  return response.data;
});
export const {
  setOnGoingResultForConversation,
  clearOnGoingResultForConversation,
  newConversation,
  addMessageToConversation,
  setSelectedConversationId,
  createNewConversation,
  deleteConversation,
  updateConversationTitle,
  setIsGenerating,
  setIsWaitingForFirstToken,
} = ConversationSlice.actions;

export const conversationSelector = (state: RootState) => ({
  conversations: state.conversationReducer.conversations,
  selectedConversationId: state.conversationReducer.selectedConversationId,
  onGoingResults: state.conversationReducer.onGoingResults,
  modelName: state.conversationReducer.modelName,
  files: state.conversationReducer.files,
  links: state.conversationReducer.links,
  isGenerating: state.conversationReducer.isGenerating,
  isWaitingForFirstToken: state.conversationReducer.isWaitingForFirstToken,
  isUploading: state.conversationReducer.isUploading,
});
export default ConversationSlice.reducer;

export const doConversation = createAsyncThunk(
  "conversation/doConversation",
  async (conversationRequest: ConversationRequest, { dispatch, getState }) => {
    const { conversationId, userPrompt } = conversationRequest;
    let selectedConversation;
    let activeConversationId: string;

    if (!conversationId) {
      // New conversation
      const id = uuidv4();
      activeConversationId = id;
      
      // First set the selected conversation ID
      dispatch(setSelectedConversationId(id));
      
      // Then create the new conversation
      dispatch(
        createNewConversation({
          title: userPrompt.content,
          id,
          message: userPrompt,
        })
      );
      
      selectedConversation = {
        conversationId: id,
        Messages: [userPrompt],
      };
    } else {
      activeConversationId = conversationId;
      dispatch(addMessageToConversation({
        conversationId: activeConversationId,
        message: userPrompt
      }));
      const state = getState() as RootState;
      selectedConversation = state.conversationReducer.conversations.find(
        (x) => x.conversationId === conversationId
      );
    }

    // Prepare messages array for backend (role, content only)
    const conversation_messages = selectedConversation?.Messages.map(msg => ({
      role: msg.role,
      content: msg.content
    })) || [];

    const body = {
      conversation_messages,
      max_tokens: MAX_TOKENS,
    };

    // Set generating state - user has submitted, waiting for AI to start responding
    dispatch(setIsGenerating({ conversationId: activeConversationId, isGenerating: true }));
    // Set waiting for first token state - critical resource usage period
    dispatch(setIsWaitingForFirstToken({ conversationId: activeConversationId, isWaiting: true }));

    let result = "";
    let firstTokenReceived = false;
    try {
      fetchEventSource(CHAT_QNA_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
        openWhenHidden: true,
        async onopen(response) {
          if (response.ok) {
            return;
          } else if (response.status >= 400 && response.status < 500 && response.status !== 429) {
            const e = await response.json();
            console.log(e);
            throw Error(e.error.message);
          } else {
            console.log("error", response);
          }
        },
        onmessage(msg) {
          if (msg?.data != "[DONE]") {
            try {
              // Keep blinking indicator active throughout streaming - it will stop in onclose() once streaming ends

              const match = msg.data.match(/b'([^']*)'/);
              if (match && match[1] != "</s>") {
                const extractedText = match[1];

                // Check for the presence of \x hexadecimal
                if (extractedText.includes("\\x")) {
                  // Decode Chinese (or other non-ASCII characters)
                  const decodedText = decodeEscapedBytes(extractedText);
                  result += decodedText;
                } else {
                  result += extractedText;
                }
              } else if (!match) {
                // Return data without pattern
                result += msg?.data;
              }
              // Store back result if it is not null
              if (result) {
                // Clear waiting for first token state when we get the first meaningful content
                if (!firstTokenReceived) {
                  dispatch(setIsWaitingForFirstToken({ conversationId: activeConversationId, isWaiting: false }));
                  firstTokenReceived = true;
                }

                dispatch(setOnGoingResultForConversation({
                  conversationId: activeConversationId,
                  result
                }));
              }
            } catch (e) {
              console.log("something wrong in msg", e);
              throw e;
            }
          }
        },
        onerror(err) {
          console.log("error", err);
          dispatch(clearOnGoingResultForConversation(activeConversationId));
          dispatch(setIsGenerating({ conversationId: activeConversationId, isGenerating: false }));
          dispatch(setIsWaitingForFirstToken({ conversationId: activeConversationId, isWaiting: false }));

          (async () => {
            const healthStatus = await checkHealth();
            const errorMessage = healthStatus.status !== 200
              ? healthStatus.message
              : err.message || 'Could not connect to backend at this moment';

            notifications.show({
              color: "red",
              message: errorMessage,
              autoClose: 5000,
            });
          })();

          throw err;
        },
        onclose() {
          dispatch(clearOnGoingResultForConversation(activeConversationId));
          dispatch(setIsGenerating({ conversationId: activeConversationId, isGenerating: false }));
          dispatch(setIsWaitingForFirstToken({ conversationId: activeConversationId, isWaiting: false }));

          dispatch(
            addMessageToConversation({
              conversationId: activeConversationId,
              message: {
                role: MessageRole.Assistant,
                content: result,
                time: getCurrentTimeStamp(),
              }
            })
          );
        },
      });
    } catch (err) {
      console.log(err);
    }
  }
);

// decode \x hexadecimal encoding
function decodeEscapedBytes(str: string): string {
  // Convert the byte portion separated by \x into a byte array and decode it into a UTF-8 string
  const byteArray: number[] = str
    .split("\\x")
    .slice(1)
    .map((byte: string) => parseInt(byte, 16));
  return new TextDecoder("utf-8").decode(new Uint8Array(byteArray));
}
