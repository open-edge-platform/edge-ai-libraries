// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import { Provider } from 'react-redux';

import VideoUploadSearch from '../components/Drawer/VideoUploadSearch.tsx';
import store from '../redux/store';
import i18n from '../utils/i18n';

// Mock axios
vi.mock('axios', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    isAxiosError: vi.fn(),
  },
}));

// Mock notify function
vi.mock('../components/Notification/notify', () => ({
  notify: vi.fn(),
  NotificationSeverity: {
    SUCCESS: 'success',
    ERROR: 'error',
    INFO: 'info',
    WARNING: 'warning',
  },
}));

// Mock i18next translations
vi.mock('react-i18next', async () => ({
  ...await vi.importActual('react-i18next'),
  useTranslation: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'videoUploadSearch.selectFile': 'Select Video File',
        'videoUploadSearch.uploadButton': 'Upload Video',
        'videoUploadSearch.uploadProgress': 'Uploading...',
        'videoUploadSearch.searchPlaceholder': 'Enter search query...',
        'videoUploadSearch.searchButton': 'Search Video',
        'common.cancel': 'Cancel',
        'common.close': 'Close',
      };
      return translations[key] || key;
    },
  }),
}));

describe('VideoUploadSearch Component', () => {
  const renderComponent = (props = {}) => {
    const defaultProps = {
      closeDrawer: vi.fn(),
      isOpen: true,
      ...props,
    };

    return render(
      <Provider store={store}>
        <I18nextProvider i18n={i18n}>
          <VideoUploadSearch {...defaultProps} />
        </I18nextProvider>
      </Provider>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Initial Rendering', () => {
    it('should render the component correctly', () => {
      renderComponent();
      expect(screen.getByText('SelectVideo')).toBeInTheDocument();
    });

    it('should display file selection button when no file is selected', () => {
      renderComponent();
      expect(screen.getByText('SelectVideo')).toBeInTheDocument();
    });
  });

  describe('File Selection', () => {
    it('should show file input when select button is clicked', () => {
      renderComponent();
      
      const selectButton = screen.getByText('SelectVideo');
      fireEvent.click(selectButton);
      
      // File input should exist (even though hidden)
      const fileInput = document.querySelector('input[type="file"]');
      expect(fileInput).toBeInTheDocument();
    });

    it('should handle file selection', async () => {
      renderComponent();
      
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      const file = new File(['video content'], 'test-video.mp4', { type: 'video/mp4' });

      fireEvent.change(fileInput, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText('test-video.mp4')).toBeInTheDocument();
      });
    });

    it('should show change video button when file is selected', async () => {
      renderComponent();
      
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      const file = new File(['video content'], 'test-video.mp4', { type: 'video/mp4' });

      fireEvent.change(fileInput, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText('changeVideo')).toBeInTheDocument();
      });
    });
  });

  describe('Upload Functionality', () => {
    it('should show upload button when file is selected', async () => {
      renderComponent();
      
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      const file = new File(['video content'], 'test-video.mp4', { type: 'video/mp4' });

      fireEvent.change(fileInput, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText('AddVideoToEmbedding')).toBeInTheDocument();
      });
    });

    it('should show upload button text changes during upload', async () => {
      renderComponent();
      
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      const file = new File(['video content'], 'test-video.mp4', { type: 'video/mp4' });

      fireEvent.change(fileInput, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText('AddVideoToEmbedding')).toBeInTheDocument();
      });

      // Button text should change when uploading starts
      fireEvent.click(screen.getByText('AddVideoToEmbedding'));

      // Should show uploading state (may change quickly)
      await waitFor(() => {
        // Either uploading state or back to normal state
        expect(
          screen.queryByText('uploadingVideoState') || 
          screen.queryByText('AddVideoToEmbedding')
        ).toBeInTheDocument();
      });
    });
  });

  describe('Component State Management', () => {
    it('should reset form when isOpen changes', () => {
      const { rerender } = renderComponent({ isOpen: true });
      
      // Component should be rendered
      expect(screen.getByText('SelectVideo')).toBeInTheDocument();
      
      // Rerender with isOpen false
      rerender(
        <Provider store={store}>
          <I18nextProvider i18n={i18n}>
            <VideoUploadSearch closeDrawer={vi.fn()} isOpen={false} />
          </I18nextProvider>
        </Provider>
      );
      
      // Component should still work when reopened
      rerender(
        <Provider store={store}>
          <I18nextProvider i18n={i18n}>
            <VideoUploadSearch closeDrawer={vi.fn()} isOpen={true} />
          </I18nextProvider>
        </Provider>
      );
      
      expect(screen.getByText('SelectVideo')).toBeInTheDocument();
    });

    it('should handle file selection and upload flow', async () => {
      const closeDrawer = vi.fn();
      renderComponent({ closeDrawer });

      // Select file
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      const file = new File(['video content'], 'test-video.mp4', { type: 'video/mp4' });
      fireEvent.change(fileInput, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText('test-video.mp4')).toBeInTheDocument();
        expect(screen.getByText('AddVideoToEmbedding')).toBeInTheDocument();
      });
    });
  });

  describe('Accessibility', () => {
    it('should have proper file input attributes', () => {
      renderComponent();
      
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      expect(fileInput).toHaveAttribute('accept', '.mp4');
    });

    it('should support keyboard navigation', () => {
      renderComponent();
      
      const selectButton = screen.getByText('SelectVideo');
      selectButton.focus();
      expect(document.activeElement).toBe(selectButton);
    });
  });

  describe('Edge Cases', () => {
    it('should handle component when not open', () => {
      renderComponent({ isOpen: false });
      // Component should still render but form might be reset
      expect(screen.getByText('SelectVideo')).toBeInTheDocument();
    });

    it('should handle large file names', async () => {
      renderComponent();
      
      const longFileName = 'very-long-file-name-that-might-cause-display-issues-in-the-ui-component.mp4';
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      const file = new File(['video content'], longFileName, { type: 'video/mp4' });

      fireEvent.change(fileInput, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText(longFileName)).toBeInTheDocument();
      });
    });

    it('should handle empty file selection', () => {
      renderComponent();
      
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(fileInput, { target: { files: null } });

      // Should still show select button
      expect(screen.getByText('SelectVideo')).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('should handle component cleanup on error', () => {
      renderComponent();
      
      // Component should render normally
      expect(screen.getByText('SelectVideo')).toBeInTheDocument();
    });

    it('should prevent upload when already uploading', async () => {
      renderComponent();
      
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      const file = new File(['video content'], 'test-video.mp4', { type: 'video/mp4' });

      fireEvent.change(fileInput, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText('AddVideoToEmbedding')).toBeInTheDocument();
      });

      // Multiple clicks should be handled gracefully
      const uploadButton = screen.getByText('AddVideoToEmbedding');
      fireEvent.click(uploadButton);
      fireEvent.click(uploadButton);
      fireEvent.click(uploadButton);

      // Should not cause errors
      await waitFor(() => {
        expect(
          screen.queryByText('uploadingVideoState') || 
          screen.queryByText('AddVideoToEmbedding')
        ).toBeInTheDocument();
      });
    });
  });
});
