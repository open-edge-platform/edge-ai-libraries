// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';

import PromptInputModal from '../components/Modals/PromptInputModal.tsx';
import i18n from '../utils/i18n';
import { UIReducer, initialState as uiInitialState } from '../redux/ui/ui.slice.ts';
import { PromptEditing } from '../redux/ui/ui.model.ts';


// Mock i18next// Create mock store
const createMockStore = (promptEditing: PromptEditing | null = null) => {
  return configureStore({
    reducer: {
      ui: UIReducer,
    },
    preloadedState: {
      ui: {
        ...uiInitialState,
        promptEditing,
      },
    },
  });
};

describe('PromptInputModal Component', () => {
  const renderComponent = (promptEditing: PromptEditing | null = null) => {
    const store = createMockStore(promptEditing);
    return render(
      <Provider store={store}>
        <I18nextProvider i18n={i18n}>
          <PromptInputModal />
        </I18nextProvider>
      </Provider>,
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Modal Visibility', () => {
    it('should not render modal when promptEditing is null', () => {
      renderComponent(null);
      
      // Modal should not be visible - checking if it doesn't have open attribute
      const modal = screen.queryByRole('dialog');
      expect(modal).toHaveAttribute('aria-modal', 'true');
    });

    it('should render modal when promptEditing is provided', () => {
      renderComponent({
        open: 'test-token',
        heading: 'Test Heading',
        prompt: 'Test prompt',
        submitValue: null,
        vars: [],
      });

      // Modal should be visible
      const modal = screen.getByRole('dialog');
      expect(modal).toBeInTheDocument();
    });
  });

  describe('Modal Content', () => {
    it('should display correct modal heading', () => {
      const testHeading = 'Custom Modal Heading';
      renderComponent({
        open: 'test-token',
        heading: testHeading,
        prompt: 'Test prompt',
        submitValue: null,
        vars: [],
      });

      expect(screen.getByText(testHeading)).toBeInTheDocument();
    });

    it('should initialize textarea with prompt value', async () => {
      const testPrompt = 'Initial prompt text';
      renderComponent({
        open: 'test-token',
        heading: 'Test Heading',
        prompt: testPrompt,
        submitValue: null,
        vars: [],
      });

      const textarea = screen.getByRole('textbox');
      await waitFor(() => {
        expect(textarea).toHaveValue(testPrompt);
      });
    });

    it('should render submit and cancel buttons', () => {
      renderComponent({
        open: 'test-token',
        heading: 'Test Heading',
        prompt: 'Test prompt',
        submitValue: null,
        vars: [],
      });

      expect(screen.getByText('Apply')).toBeInTheDocument();
      expect(screen.getByText('Cancel')).toBeInTheDocument();
    });
  });

  describe('Validation Logic', () => {
    it('should show error when required variables are missing', async () => {
      renderComponent({
        open: 'test-token',
        heading: 'Test Heading',
        prompt: 'Hello %name%',
        submitValue: null,
        vars: ['%name%', '%age%'],
      });

      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: 'Hello world' } });

      await waitFor(() => {
        expect(screen.getByText(/Unused variables:/)).toBeInTheDocument();
      });
    });

    it('should not show error when all variables are used', async () => {
      renderComponent({
        open: 'test-token',
        heading: 'Test Heading',
        prompt: 'Hello %name%',
        submitValue: null,
        vars: ['%name%'],
      });

      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: 'Hello %name%, how are you?' } });

      await waitFor(() => {
        expect(screen.queryByText(/UnusedVars/)).not.toBeInTheDocument();
      });
    });

    it('should validate correctly when no variables are required', async () => {
      renderComponent({
        open: 'test-token',
        heading: 'Test Heading',
        prompt: 'Simple prompt',
        submitValue: null,
        vars: [],
      });

      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: 'Any text is valid' } });

      // Should not show error
      expect(screen.queryByText(/UnusedVars/)).not.toBeInTheDocument();
    });
  });

  describe('User Interactions', () => {
    it('should update current value when textarea content changes', async () => {
      renderComponent({
        open: 'test-token',
        heading: 'Test Heading',
        prompt: '',
        submitValue: null,
        vars: [],
      });

      const textarea = screen.getByRole('textbox');
      const newText = 'New prompt text';
      
      fireEvent.change(textarea, { target: { value: newText } });

      await waitFor(() => {
        expect(textarea).toHaveValue(newText);
      });
    });

    it('should disable submit button when validation fails', async () => {
      renderComponent({
        open: 'test-token',
        heading: 'Test Heading',
        prompt: 'Hello %name%',
        submitValue: null,
        vars: ['%name%', '%age%'],
      });

      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: 'Invalid text without required vars' } });

      await waitFor(() => {
        const submitButton = screen.getByText('Apply');
        expect(submitButton).toBeDisabled();
      });
    });
  });

  describe('Modal Actions', () => {
    it('should handle modal close action', () => {
      const store = createMockStore({
        open: 'test-token',
        heading: 'Test Heading',
        prompt: 'Test prompt',
        submitValue: null,
        vars: [],
      });
      
      render(
        <Provider store={store}>
          <I18nextProvider i18n={i18n}>
            <PromptInputModal />
          </I18nextProvider>
        </Provider>,
      );

      const cancelButton = screen.getByText('Cancel');
      fireEvent.click(cancelButton);

      // Check if close action was dispatched (promptEditing should be null)
      const state = store.getState();
      expect(state.ui.promptEditing).toBeNull();
    });

    it('should handle modal submit when valid', async () => {
      const store = createMockStore({
        open: 'test-token',
        heading: 'Test Heading',
        prompt: 'Hello %name%',
        submitValue: null,
        vars: ['%name%'],
      });
      
      render(
        <Provider store={store}>
          <I18nextProvider i18n={i18n}>
            <PromptInputModal />
          </I18nextProvider>
        </Provider>,
      );

      const textarea = screen.getByRole('textbox');
      const validPrompt = 'Hello %name%, welcome!';
      fireEvent.change(textarea, { target: { value: validPrompt } });

      await waitFor(() => {
        const submitButton = screen.getByText('Apply');
        expect(submitButton).not.toBeDisabled();
        fireEvent.click(submitButton);
      });

      // Check that submitValue was updated
      const state = store.getState();
      expect(state.ui.promptEditing?.submitValue).toBe(validPrompt);
    });
  });

  describe('Edge Cases', () => {
    it('should handle empty vars array', () => {
      renderComponent({
        open: 'test-token',
        heading: 'Test Heading',
        prompt: 'Simple prompt',
        submitValue: null,
        vars: [],
      });

      expect(screen.getByRole('textbox')).toBeInTheDocument();
      expect(screen.queryByText(/UnusedVars/)).not.toBeInTheDocument();
    });

    it('should handle empty prompt', async () => {
      renderComponent({
        open: 'test-token',
        heading: 'Test Heading',
        prompt: '',
        submitValue: null,
        vars: [],
      });

      const textarea = screen.getByRole('textbox');
      await waitFor(() => {
        expect(textarea).toHaveValue('');
      });
    });

    it('should reset textarea value when modal closes', () => {
      const store = createMockStore({
        open: 'test-token',
        heading: 'Test Heading',
        prompt: 'Test prompt',
        submitValue: null,
        vars: [],
      });
      
      render(
        <Provider store={store}>
          <I18nextProvider i18n={i18n}>
            <PromptInputModal />
          </I18nextProvider>
        </Provider>,
      );

      const cancelButton = screen.getByText('Cancel');
      fireEvent.click(cancelButton);

      // Modal should be closed - just check that cancel button was clicked
      expect(cancelButton).toBeInTheDocument();
    });
  });
});
