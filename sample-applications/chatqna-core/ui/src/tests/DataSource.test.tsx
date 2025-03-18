// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { it, describe, expect, afterEach, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import { Provider } from 'react-redux';
import { configureStore, unwrapResult } from '@reduxjs/toolkit';

import DataSource from '../components/Drawer/DataSource.tsx';
import i18n from '../utils/i18n';
import {
  notify,
  NotificationSeverity,
} from '../components/Notification/notify.ts';
import conversationReducer, {
  fetchInitialFiles,
  uploadFile,
} from '../redux/conversation/conversationSlice.ts';
import { MAX_FILE_SIZE } from '../utils/constant.ts';

vi.mock('../components/Notification/notify.ts', () => ({
  notify: vi.fn(),
  NotificationSeverity: {
    WARNING: 'warning',
    ERROR: 'error',
    INFO: 'info',
  },
}));

vi.mock('@reduxjs/toolkit', async () => {
  const actual = await vi.importActual('@reduxjs/toolkit');
  return {
    ...actual,
    unwrapResult: vi.fn(),
  };
});

vi.mock('../redux/conversation/conversationSlice.ts', async () => {
  const actual = await vi.importActual(
    '../redux/conversation/conversationSlice.ts',
  );
  return {
    ...actual,
    uploadFile: vi.fn(),
    fetchInitialFiles: vi.fn(),
  };
});

describe('DataSource Component test suite', () => {
  let store: ReturnType<typeof configureStore>;
  const mockClose = vi.fn();
  const mockUploadFile = vi.fn();
  const mockFetchInitialFiles = vi.fn();
  const mockUnwrapResult = vi.fn();

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
          <DataSource close={mockClose} />
        </I18nextProvider>
      </Provider>,
    );
  };

  afterEach(() => {
    vi.clearAllMocks();
    vi.mocked(uploadFile).mockReturnValue(mockUploadFile);
    vi.mocked(fetchInitialFiles).mockReturnValue(mockFetchInitialFiles);
    vi.mocked(unwrapResult).mockReturnValue(mockUnwrapResult);
  });

  it('should render the component correctly', () => {
    renderComponent();

    expect(screen.getByTestId('data-source-wrapper')).toBeInTheDocument();
  });

  it('should handle file selection and display file name', () => {
    renderComponent();

    const file = new File(['dummy content'], 'example.txt', {
      type: 'text/plain',
    });
    const input = screen.getByTestId('file-input-field') as HTMLInputElement;

    fireEvent.change(input, { target: { files: [file] } });

    expect(screen.getByTestId('file-container')).toBeInTheDocument();
    expect(screen.getByText('example.txt')).toBeInTheDocument();
    expect(screen.getByTestId('file-upload-button')).not.toBeDisabled();
  });

  it('should handle file upload successfully', async () => {
    renderComponent();

    const file = new File(['dummy content'], 'example.txt', {
      type: 'text/plain',
    });
    const fileInput = screen.getByTestId('file-input-field');

    fireEvent.change(fileInput, { target: { files: [file] } });

    const uploadButton = screen.getByTestId('file-upload-button');
    fireEvent.click(uploadButton);

    await waitFor(() => {
      expect(mockClose).toHaveBeenCalled();
      expect(uploadFile).toHaveBeenCalledWith({ file });
      expect(notify).toHaveBeenNthCalledWith(
        1,
        expect.stringMatching(new RegExp(i18n.t('fileUploadStarted'), 'i')),
        NotificationSeverity.INFO,
      );
    });
  });

  it('should handle invalid file format', () => {
    renderComponent();

    const file = new File(['dummy content'], 'example.exe', {
      type: 'application/x-msdownload',
    });
    const input = screen.getByTestId('file-input-field') as HTMLInputElement;

    fireEvent.change(input, { target: { files: [file] } });

    expect(notify).toHaveBeenCalledWith(
      i18n.t('formatNotification'),
      NotificationSeverity.ERROR,
    );
    expect(screen.queryByTestId('file-container')).not.toBeInTheDocument();
  });

  it('should handle file size exceeding limit', () => {
    renderComponent();

    const file = new File(
      ['a'.repeat(MAX_FILE_SIZE * 1024 * 1024 + 1)],
      'largefile.txt',
      { type: 'text/plain' },
    );
    const input = screen.getByTestId('file-input-field') as HTMLInputElement;

    fireEvent.change(input, { target: { files: [file] } });

    expect(notify).toHaveBeenCalledWith(
      i18n.t('fileSizeExceeded'),
      NotificationSeverity.WARNING,
    );
    expect(screen.queryByTestId('file-container')).not.toBeInTheDocument();
  });

  it('should clear file input when no file is selected', () => {
    renderComponent();

    const input = screen.getByTestId('file-input-field') as HTMLInputElement;

    fireEvent.change(input, { target: { files: [] } });

    expect(input.value).toBe('');
    expect(screen.queryByTestId('file-container')).not.toBeInTheDocument();
  });
});
