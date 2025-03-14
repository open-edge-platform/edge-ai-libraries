// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import { it, describe, expect, afterEach, vi } from 'vitest';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';

import i18n from '../utils/i18n';
import conversationReducer from '../redux/conversation/conversationSlice.ts';
import FileList from '../components/Drawer/FileList.tsx';

vi.mock('../../components/Notification/notify.ts', () => ({
  notify: vi.fn(),
}));

describe('FileList Component test suite', () => {
  let store: ReturnType<typeof configureStore>;
  const closeDrawerMock = vi.fn();

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
          <FileList closeDrawer={closeDrawerMock} isOpen={true} />
        </I18nextProvider>
      </Provider>,
    );
  };

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should render the component correctly', () => {
    renderComponent();

    expect(screen.getByTestId('file-tabs')).toBeInTheDocument();
    expect(screen.getByTestId('link-tabs')).toBeInTheDocument();
  });

  it('should display no files message when there are no files', () => {
    renderComponent();

    expect(screen.getByText(i18n.t('noFilesFound'))).toBeInTheDocument();
  });

  it('should show file upload form when add new file button is clicked', () => {
    renderComponent();

    const addButton = screen.getByTestId('add-new-file-button');
    fireEvent.click(addButton);

    expect(
      screen.getByText(i18n.t('uploadFileDescription')),
    ).toBeInTheDocument();
    expect(screen.getByTestId('add-file-button')).toBeInTheDocument();
  });

  it('should display no links message when there are no links', () => {
    renderComponent();

    fireEvent.click(screen.getByTestId('link-tabs'));

    expect(screen.getByText(i18n.t('noLinksFound'))).toBeInTheDocument();
  });

  it('should show link upload textarea when add new link button is clicked', () => {
    renderComponent();

    fireEvent.click(screen.getByTestId('link-tabs'));

    const addButton = screen.getByTestId('add-new-file-button');
    fireEvent.click(addButton);

    expect(
      screen.getByText(i18n.t('uploadLinkDescription')),
    ).toBeInTheDocument();
    expect(screen.getByTestId('link-data-source-wrapper')).toBeInTheDocument();
  });
});
