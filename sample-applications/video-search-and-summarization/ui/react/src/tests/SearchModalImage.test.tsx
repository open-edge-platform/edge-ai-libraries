// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';

// Image search is gated on FEATURE_SEARCH being ON and the mux not being the
// unified (SUMMARY_SEARCH) layout. Mock the build-time config so the image
// controls render in this suite (they are hidden by default in test env).
vi.mock('../config', () => ({
  APP_URL: 'http://localhost/manager',
  ASSETS_ENDPOINT: 'http://localhost/assets',
  SOCKET_APPEND: '',
  FEATURE_SUMMARY: 'FEATURE_OFF',
  FEATURE_SEARCH: 'FEATURE_ON',
  FEATURE_MUX: 'ATOMIC',
  FEATURE_CAMERA_CONFIG: 'FEATURE_OFF',
  NVR_API_BASE: '',
}));

import { SearchModal, SearchModalProps } from '../components/PopupModal/SearchModal';
import { SearchReducers } from '../redux/search/searchSlice.ts';
import i18n from '../utils/i18n';

const mockDispatch = vi.fn();

const createMockStore = () =>
  configureStore({
    reducer: { search: SearchReducers },
    preloadedState: {
      search: {
        searchQueries: [],
        selectedQuery: null,
        suggestedTags: [],
        unreads: [],
        triggerLoad: false,
      },
    },
  });

const defaultProps: SearchModalProps = {
  showModal: true,
  closeModal: vi.fn(),
};

const renderComponent = (props: Partial<SearchModalProps> = {}) => {
  const store = createMockStore();
  store.dispatch = mockDispatch;
  return render(
    <Provider store={store}>
      <I18nextProvider i18n={i18n}>
        <SearchModal {...defaultProps} {...props} />
      </I18nextProvider>
    </Provider>,
  );
};

const getFileInput = (container: HTMLElement) =>
  container.querySelector('input[type="file"]') as HTMLInputElement;

const makeFile = (name: string, type: string, sizeBytes?: number) => {
  const file = new File(['image-bytes'], name, { type });
  if (sizeBytes != null) {
    Object.defineProperty(file, 'size', { value: sizeBytes });
  }
  return file;
};

describe('SearchModal image search', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // jsdom lacks a canvas backend and does not auto-fire Image load, so stub
    // the browser primitives processImageFile relies on for the happy path.
    (URL as unknown as { createObjectURL: unknown }).createObjectURL = vi.fn(
      () => 'blob:mock',
    );
    (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn();
    HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
      drawImage: vi.fn(),
    })) as unknown as HTMLCanvasElement['getContext'];
    HTMLCanvasElement.prototype.toDataURL = vi.fn(
      () => 'data:image/jpeg;base64,QUJD',
    );
    vi.stubGlobal(
      'Image',
      class {
        onload: (() => void) | null = null;
        onerror: (() => void) | null = null;
        width = 120;
        height = 90;
        set src(_value: string) {
          // Mimic an async, successful decode.
          setTimeout(() => this.onload?.(), 0);
        }
      },
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('renders the upload control when image search is enabled', () => {
    renderComponent();
    expect(screen.getByText('Upload query image')).toBeInTheDocument();
  });

  it('rejects an unsupported file type with a validation error', async () => {
    const { container } = renderComponent();
    fireEvent.change(getFileInput(container), {
      target: { files: [makeFile('notes.txt', 'text/plain')] },
    });

    await waitFor(() => {
      expect(
        screen.getByText('Unsupported image type. Use JPG, PNG, or WEBP.'),
      ).toBeInTheDocument();
    });
    // The text area is still shown (no preview) after a rejected file.
    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });

  it('rejects an oversized image with a validation error', async () => {
    const { container } = renderComponent();
    fireEvent.change(getFileInput(container), {
      target: { files: [makeFile('big.png', 'image/png', 11 * 1024 * 1024)] },
    });

    await waitFor(() => {
      expect(
        screen.getByText('Image is too large. Maximum size is 10 MB.'),
      ).toBeInTheDocument();
    });
  });

  it('swaps the text area for a preview when a valid image is chosen', async () => {
    const { container } = renderComponent();
    fireEvent.change(getFileInput(container), {
      target: { files: [makeFile('frame.png', 'image/png')] },
    });

    // Preview appears...
    await waitFor(() => {
      expect(screen.getByAltText('Search by image')).toBeInTheDocument();
    });
    // ...and the text area is removed to reclaim the space.
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('dispatches a search when submitting with an image', async () => {
    const closeModalMock = vi.fn();
    const { container } = renderComponent({ closeModal: closeModalMock });
    fireEvent.change(getFileInput(container), {
      target: { files: [makeFile('frame.png', 'image/png')] },
    });

    await waitFor(() => {
      expect(screen.getByAltText('Search by image')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Search'));

    await waitFor(() => {
      expect(mockDispatch).toHaveBeenCalled();
      expect(closeModalMock).toHaveBeenCalled();
    });
  });

  it('restores the preserved text query after removing the image', async () => {
    renderComponent();

    // Type a query, then attach an image (which hides the text area).
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'red bus' },
    });
    fireEvent.change(
      document.querySelector('input[type="file"]') as HTMLInputElement,
      { target: { files: [makeFile('frame.png', 'image/png')] } },
    );

    await waitFor(() => {
      expect(screen.getByAltText('Search by image')).toBeInTheDocument();
    });
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();

    // Remove the image -> the text area returns with the preserved query.
    fireEvent.click(screen.getByRole('button', { name: /remove image/i }));

    const restored = screen.getByRole('textbox') as HTMLTextAreaElement;
    expect(restored).toBeInTheDocument();
    expect(restored.value).toBe('red bus');
  });
});
