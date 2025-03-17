// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { render, screen, fireEvent } from '@testing-library/react';
import { it, describe, expect, afterEach, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import { Provider, useDispatch } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';

import i18n from '../utils/i18n';
import conversationReducer from '../redux/conversation/conversationSlice.ts';
import FileLinkManager from '../components/Drawer/FileLinkManager.tsx';

vi.mock('../components/Notification/notify.ts', () => ({
  notify: vi.fn(),
  NotificationSeverity: {
    SUCCESS: 'success',
    ERROR: 'error',
  },
}));

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
    removeFile: vi.fn(),
    removeAllFiles: vi.fn(),
    removeLink: vi.fn(),
    removeAllLinks: vi.fn(),
    conversationSelector: vi.fn((state) => state.conversation),
  };
});

vi.mock('@reduxjs/toolkit', async () => {
  const actual = await vi.importActual('@reduxjs/toolkit');
  return {
    ...actual,
    unwrapResult: vi.fn(),
  };
});

describe('FileLinkManager Component test suite', () => {
  const mockDispatch = vi.fn();
  const closeDrawerMock = vi.fn();
  let store: ReturnType<typeof configureStore>;

  const renderComponent = (
    initialState = {},
    showField = false,
    isFile = true,
  ) => {
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
          <FileLinkManager
            closeDrawer={closeDrawerMock}
            showField={showField}
            isFile={isFile}
          />
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

    expect(screen.getByTestId('file-link-manager-wrapper')).toBeInTheDocument();
  });

  it('should display files when there are files', () => {
    const initialState = {
      files: [
        { file_name: 'file1.txt', bucket_name: 'bucket' },
        { file_name: 'file2.txt', bucket_name: 'bucket' },
      ],
    };
    renderComponent(initialState);

    expect(screen.getByText('file1.txt')).toBeInTheDocument();
    expect(screen.getByText('file2.txt')).toBeInTheDocument();
  });

  it('should handle file selection', () => {
    const initialState = {
      files: [
        { file_name: 'file1.txt', bucket_name: 'bucket' },
        { file_name: 'file2.txt', bucket_name: 'bucket' },
      ],
    };
    renderComponent(initialState);

    const checkbox = screen.getAllByRole('checkbox')[0];
    fireEvent.click(checkbox);

    expect(checkbox).toBeChecked();
  });

  it('should open modal when delete selected button is clicked', () => {
    const initialState = {
      files: [
        { file_name: 'file1.txt', bucket_name: 'bucket' },
        { file_name: 'file2.txt', bucket_name: 'bucket' },
      ],
    };
    renderComponent(initialState);

    const checkbox = screen.getAllByRole('checkbox')[0];
    fireEvent.click(checkbox);

    const deleteSelectedButton = screen.getByTestId(
      'handle-delete-selected-button',
    );
    fireEvent.click(deleteSelectedButton);

    expect(screen.getByText(i18n.t('deleteFiles'))).toBeInTheDocument();
  });

  it('should open modal when delete all button is clicked', () => {
    const initialState = {
      files: [
        { file_name: 'file1.txt', bucket_name: 'bucket' },
        { file_name: 'file2.txt', bucket_name: 'bucket' },
      ],
    };
    renderComponent(initialState);

    const deleteAllButton = screen.getByTestId('handle-delete-all-button');
    fireEvent.click(deleteAllButton);

    expect(screen.getByText(i18n.t('deleteFiles'))).toBeInTheDocument();
  });

  it('should display links when there are links', () => {
    const initialState = {
      links: ['https://www.example1.com', 'https://www.example2.com'],
    };
    renderComponent(initialState, false, false);

    expect(screen.getByText('https://www.example1.com')).toBeInTheDocument();
    expect(screen.getByText('https://www.example2.com')).toBeInTheDocument();
  });

  it('should handle link selection', () => {
    const initialState = {
      links: ['https://www.example1.com', 'https://www.example2.com'],
    };
    renderComponent(initialState, false, false);

    const checkbox = screen.getAllByRole('checkbox')[0];
    fireEvent.click(checkbox);

    expect(checkbox).toBeChecked();
  });

  it('should open modal when delete selected links button is clicked', () => {
    const initialState = {
      links: ['https://www.example1.com', 'https://www.example2.com'],
    };
    renderComponent(initialState, false, false);

    const checkbox = screen.getAllByRole('checkbox')[0];
    fireEvent.click(checkbox);

    const deleteSelectedButton = screen.getByTestId(
      'handle-delete-selected-button',
    );
    fireEvent.click(deleteSelectedButton);

    expect(screen.getByText(i18n.t('deleteLinks'))).toBeInTheDocument();
  });

  it('should open modal when delete all links button is clicked', () => {
    const initialState = {
      links: ['https://www.example1.com', 'https://www.example2.com'],
    };
    renderComponent(initialState, false, false);

    const deleteAllButton = screen.getByTestId('handle-delete-all-button');
    fireEvent.click(deleteAllButton);

    expect(screen.getByText(i18n.t('deleteLinks'))).toBeInTheDocument();
  });
});
