// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { it, describe, expect, afterEach, vi, beforeEach } from 'vitest';
import { I18nextProvider } from 'react-i18next';
import { Provider, useDispatch } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { AxiosError } from 'axios';

import i18n from '../utils/i18n';
import conversationReducer from '../redux/conversation/conversationSlice.ts';
import FileLinkManager from '../components/Drawer/FileLinkManager.tsx';
import {
  NotificationSeverity,
  notify,
} from '../components/Notification/notify.ts';

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

  const renderComponent = (initialState = {}, showField = false) => {
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
          <FileLinkManager
            closeDrawer={closeDrawerMock}
            showField={showField}
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
      files: ['file1.txt', 'file2.txt'],
    };
    renderComponent(initialState);

    expect(screen.getByText('file1.txt')).toBeInTheDocument();
    expect(screen.getByText('file2.txt')).toBeInTheDocument();
  });

  it('should handle file selection', () => {
    const initialState = {
      files: ['file1.txt', 'file2.txt'],
    };
    renderComponent(initialState);

    const checkbox1 = screen.getAllByRole('checkbox')[0];
    fireEvent.click(checkbox1);

    expect(checkbox1).toBeChecked();
  });

  it('should open modal when delete selected button is clicked', () => {
    const initialState = {
      files: ['file1.txt', 'file2.txt'],
    };
    renderComponent(initialState);

    const checkbox = screen.getAllByRole('checkbox')[0];
    fireEvent.click(checkbox);

    const deleteSelectedButton = screen.getByTestId(
      i18n.t('handle-delete-selected-button'),
    );
    fireEvent.click(deleteSelectedButton);

    expect(screen.getByText(i18n.t('deleteFiles'))).toBeInTheDocument();
  });

  it('should open modal when delete all button is clicked', () => {
    const initialState = {
      files: ['file1.txt', 'file2.txt'],
    };
    renderComponent(initialState);

    const deleteAllButton = screen.getByTestId(
      i18n.t('handle-delete-all-button'),
    );
    fireEvent.click(deleteAllButton);

    expect(screen.getByText(i18n.t('deleteFiles'))).toBeInTheDocument();
  });

  it('should handle confirm delete selected files', async () => {
    const initialState = {
      files: ['file1.txt', 'file2.txt'],
    };
    renderComponent(initialState);

    const checkbox = screen.getAllByRole('checkbox')[0];
    fireEvent.click(checkbox);

    const deleteSelectedButton = screen.getByTestId(
      i18n.t('handle-delete-selected-button'),
    );
    fireEvent.click(deleteSelectedButton);

    const confirmButton = screen.getByText(i18n.t('confirm'));
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(notify).toHaveBeenCalledWith(
        `${i18n.t('file')} file1.txt ${i18n.t('deletedSuccessfully')}`,
        NotificationSeverity.SUCCESS,
      );
    });
  });

  it('should handle confirm delete all files', async () => {
    const initialState = {
      files: ['file1.txt', 'file2.txt'],
    };
    renderComponent(initialState);

    const deleteAllButton = screen.getByTestId(
      i18n.t('handle-delete-all-button'),
    );
    fireEvent.click(deleteAllButton);

    const confirmButton = screen.getByText(i18n.t('confirm'));
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(notify).toHaveBeenCalledWith(
        i18n.t('filesSuccessfullyDeleted'),
        NotificationSeverity.SUCCESS,
      );
    });
  });

  it('should handle delete selected files error', async () => {
    const initialState = {
      files: ['file1.txt', 'file2.txt'],
    };
    renderComponent(initialState);

    mockDispatch.mockRejectedValueOnce(new AxiosError('Delete failed'));

    const checkbox1 = screen.getAllByRole('checkbox')[0];
    fireEvent.click(checkbox1);

    const deleteSelectedButton = screen.getByTestId(
      i18n.t('handle-delete-selected-button'),
    );
    fireEvent.click(deleteSelectedButton);

    const confirmButton = screen.getByText(i18n.t('confirm'));
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(notify).toHaveBeenCalledWith(
        'Delete failed',
        NotificationSeverity.ERROR,
      );
    });
  });

  it('should handle delete all files error', async () => {
    const initialState = {
      files: ['file1.txt', 'file2.txt'],
    };
    renderComponent(initialState);

    mockDispatch.mockRejectedValueOnce(new AxiosError('Delete failed'));

    const deleteAllButton = screen.getByTestId(
      i18n.t('handle-delete-all-button'),
    );
    fireEvent.click(deleteAllButton);

    const confirmButton = screen.getByText(i18n.t('confirm'));
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(notify).toHaveBeenCalledWith(
        'Delete failed',
        NotificationSeverity.ERROR,
      );
    });
  });
});
