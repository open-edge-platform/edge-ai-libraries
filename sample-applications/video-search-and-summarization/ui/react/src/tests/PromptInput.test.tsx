// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { Provider } from 'react-redux';
import { I18nextProvider } from 'react-i18next';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { configureStore } from '@reduxjs/toolkit';
import { PromptInput, PromptInputProps } from '../components/Prompts/PromptInput';
import { UIActions, UISlice, initialState as uiInitialState } from '../redux/ui/ui.slice';
import { UISliceState } from '../redux/ui/ui.model';
import i18n from '../utils/i18n';

// Mock Carbon components
vi.mock('@carbon/react', () => ({
  IconButton: ({ onClick, children, label, size, kind }: any) => (
    <button data-testid={`icon-button-${label}`} onClick={onClick} data-size={size} data-kind={kind}>
      {children}
    </button>
  ),
  Toggletip: ({ children }: any) => <div data-testid="toggletip">{children}</div>,
  ToggletipButton: ({ onClick, children, label }: any) => (
    <button data-testid={`toggletip-button-${label}`} onClick={onClick}>
      {children}
    </button>
  ),
  ToggletipContent: ({ children }: any) => <div data-testid="toggletip-content">{children}</div>,
}));

// Mock Carbon icons
vi.mock('@carbon/icons-react', () => ({
  Edit: () => <div data-testid="edit-icon">Edit</div>,
  Information: () => <div data-testid="information-icon">Information</div>,
  Reset: () => <div data-testid="reset-icon">Reset</div>,
}));


// Mock react-i18next
vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
      i18n: {
        changeLanguage: () => new Promise(() => {}),
      },
    }),
  };
});

// Create mock store
const createMockStore = (initialState: Partial<UISliceState> = {}) => {
  return configureStore({
    reducer: {
      ui: UISlice.reducer,
    },
    preloadedState: {
      ui: {
        ...uiInitialState,
        ...initialState,
      },
    },
  });
};

const defaultProps: PromptInputProps = {
  label: 'Test Label',
  defaultVal: 'Default Value',
  prompt: 'Test Prompt',
  infoLabel: 'Info Label',
  description: 'Test Description',
  opener: 'TEST_OPENER',
  editHeading: 'Edit Heading',
  onChange: vi.fn(),
  reset: vi.fn(),
};

const renderWithProviders = (component: React.ReactElement, store: any) => {
  return render(
    <Provider store={store}>
      <I18nextProvider i18n={i18n}>
        {component}
      </I18nextProvider>
    </Provider>
  );
};

describe('PromptInput Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Rendering', () => {
    it('should render the component with basic props', () => {
      const store = createMockStore();
      renderWithProviders(<PromptInput {...defaultProps} />, store);

      expect(screen.getByText('Test Label')).toBeInTheDocument();
      expect(screen.getByTestId('icon-button-editPrompt')).toBeInTheDocument();
      expect(screen.getByTestId('toggletip-button-Info Label')).toBeInTheDocument();
      expect(screen.getByTestId('toggletip')).toBeInTheDocument();
    });

    it('should render edit icon button with correct properties', () => {
      const store = createMockStore();
      renderWithProviders(<PromptInput {...defaultProps} />, store);

      const editButton = screen.getByTestId('icon-button-editPrompt');
      expect(editButton).toHaveAttribute('data-size', 'sm');
      expect(editButton).toHaveAttribute('data-kind', 'ghost');
      expect(screen.getByTestId('edit-icon')).toBeInTheDocument();
    });

    it('should render information toggletip with content', () => {
      const store = createMockStore();
      renderWithProviders(<PromptInput {...defaultProps} />, store);

      expect(screen.getByTestId('toggletip-button-Info Label')).toBeInTheDocument();
      expect(screen.getByTestId('information-icon')).toBeInTheDocument();
      expect(screen.getByTestId('toggletip-content')).toBeInTheDocument();
      expect(screen.getByText('Test Description')).toBeInTheDocument();
      expect(screen.getByText('promptHeading')).toBeInTheDocument();
      expect(screen.getByText('Test Prompt')).toBeInTheDocument();
    });

    it('should render spacer element', () => {
      const store = createMockStore();
      renderWithProviders(<PromptInput {...defaultProps} />, store);

      const spacer = document.querySelector('.spacer');
      expect(spacer).toBeInTheDocument();
    });
  });

  describe('Reset Button Functionality', () => {
    it('should show reset button when prompt differs from default value', () => {
      const store = createMockStore();
      const props = { ...defaultProps, prompt: 'Modified Prompt' };
      renderWithProviders(<PromptInput {...props} />, store);

      expect(screen.getByTestId('icon-button-ResetDefault')).toBeInTheDocument();
      expect(screen.getByTestId('reset-icon')).toBeInTheDocument();
    });

    it('should not show reset button when prompt equals default value', () => {
      const store = createMockStore();
      const props = { ...defaultProps, prompt: 'Default Value' };
      renderWithProviders(<PromptInput {...props} />, store);

      expect(screen.queryByTestId('icon-button-ResetDefault')).not.toBeInTheDocument();
    });

    it('should call reset function when reset button is clicked', () => {
      const store = createMockStore();
      const resetMock = vi.fn();
      const props = { ...defaultProps, prompt: 'Modified Prompt', reset: resetMock };
      renderWithProviders(<PromptInput {...props} />, store);

      const resetButton = screen.getByTestId('icon-button-ResetDefault');
      fireEvent.click(resetButton);

      expect(resetMock).toHaveBeenCalledOnce();
    });

    it('should render reset button with correct properties', () => {
      const store = createMockStore();
      const props = { ...defaultProps, prompt: 'Modified Prompt' };
      renderWithProviders(<PromptInput {...props} />, store);

      const resetButton = screen.getByTestId('icon-button-ResetDefault');
      expect(resetButton).toHaveAttribute('data-size', 'sm');
      expect(resetButton).toHaveAttribute('data-kind', 'ghost');
    });
  });

  describe('Edit Button Functionality', () => {
    it('should dispatch openPromptModal action when edit button is clicked', () => {
      const store = createMockStore();
      const spy = vi.spyOn(store, 'dispatch');
      renderWithProviders(<PromptInput {...defaultProps} />, store);

      const editButton = screen.getByTestId('icon-button-editPrompt');
      fireEvent.click(editButton);

      expect(spy).toHaveBeenCalledWith({
        type: 'ui/openPromptModal',
        payload: {
          heading: 'Edit Heading',
          openToken: 'TEST_OPENER',
          prompt: 'Test Prompt',
        },
      });
    });

    it('should handle edit button click with different props', () => {
      const store = createMockStore();
      const spy = vi.spyOn(store, 'dispatch');
      const customProps = {
        ...defaultProps,
        editHeading: 'Custom Edit Heading',
        opener: 'CUSTOM_OPENER',
        prompt: 'Custom Prompt',
      };
      renderWithProviders(<PromptInput {...customProps} />, store);

      const editButton = screen.getByTestId('icon-button-editPrompt');
      fireEvent.click(editButton);

      expect(spy).toHaveBeenCalledWith({
        type: 'ui/openPromptModal',
        payload: {
          heading: 'Custom Edit Heading',
          openToken: 'CUSTOM_OPENER',
          prompt: 'Custom Prompt',
        },
      });
    });
  });

  describe('useEffect Hook for Prompt Submission', () => {
    it('should call onChange when promptSubmitValue matches openerToken', async () => {
      const onChangeMock = vi.fn();
      const store = createMockStore({
        promptEditing: {
          open: 'TEST_OPENER',
          heading: 'Test Heading',
          prompt: 'Test Prompt',
          submitValue: 'Submitted Value',
          vars: [],
        },
      });
      const spy = vi.spyOn(store, 'dispatch');

      renderWithProviders(<PromptInput {...defaultProps} onChange={onChangeMock} />, store);

      await waitFor(() => {
        expect(onChangeMock).toHaveBeenCalledWith('Submitted Value');
        expect(spy).toHaveBeenCalledWith({ type: 'ui/closePrompt' });
      });
    });

    it('should not call onChange when openerToken does not match', () => {
      const onChangeMock = vi.fn();
      const store = createMockStore({
        promptEditing: {
          open: 'DIFFERENT_OPENER',
          heading: 'Test Heading',
          prompt: 'Test Prompt',
          submitValue: 'Submitted Value',
          vars: [],
        },
      });

      renderWithProviders(<PromptInput {...defaultProps} onChange={onChangeMock} />, store);

      expect(onChangeMock).not.toHaveBeenCalled();
    });

    it('should not call onChange when promptSubmitValue is empty', () => {
      const onChangeMock = vi.fn();
      const store = createMockStore({
        promptEditing: {
          open: 'TEST_OPENER',
          heading: 'Test Heading',
          prompt: 'Test Prompt',
          submitValue: null,
          vars: [],
        },
      });

      renderWithProviders(<PromptInput {...defaultProps} onChange={onChangeMock} />, store);

      expect(onChangeMock).not.toHaveBeenCalled();
    });

    it('should handle multiple prompt submissions correctly', async () => {
      const onChangeMock = vi.fn();
      const store = createMockStore();

      renderWithProviders(
        <PromptInput {...defaultProps} onChange={onChangeMock} />,
        store
      );

      // First submission
      act(() => {
        store.dispatch(UIActions.openPromptModal({
          heading: 'Test Heading',
          openToken: 'TEST_OPENER',
          prompt: 'Test Prompt',
        }));
        store.dispatch(UIActions.submitPromptModal('First Value'));
      });

      await waitFor(() => {
        expect(onChangeMock).toHaveBeenCalledWith('First Value');
      });

      // Second submission with different opener
      onChangeMock.mockClear();
      act(() => {
        store.dispatch(UIActions.openPromptModal({
          heading: 'Test Heading',
          openToken: 'DIFFERENT_OPENER',
          prompt: 'Test Prompt',
        }));
        store.dispatch(UIActions.submitPromptModal('Second Value'));
      });

      expect(onChangeMock).not.toHaveBeenCalled();
    });
  });

  describe('Component Props Variations', () => {
    it('should render with different label text', () => {
      const store = createMockStore();
      const props = { ...defaultProps, label: 'Custom Label' };
      renderWithProviders(<PromptInput {...props} />, store);

      expect(screen.getByText('Custom Label')).toBeInTheDocument();
    });

    it('should render with different info label', () => {
      const store = createMockStore();
      const props = { ...defaultProps, infoLabel: 'Custom Info Label' };
      renderWithProviders(<PromptInput {...props} />, store);

      expect(screen.getByTestId('toggletip-button-Custom Info Label')).toBeInTheDocument();
    });

    it('should render with different description and prompt in toggletip content', () => {
      const store = createMockStore();
      const props = { 
        ...defaultProps, 
        description: 'Custom Description',
        prompt: 'Custom Prompt Content'
      };
      renderWithProviders(<PromptInput {...props} />, store);

      expect(screen.getByText('Custom Description')).toBeInTheDocument();
      expect(screen.getByText('Custom Prompt Content')).toBeInTheDocument();
    });

    it('should handle empty string props gracefully', () => {
      const store = createMockStore();
      const props = { 
        ...defaultProps, 
        label: '',
        description: '',
        prompt: ''
      };
      renderWithProviders(<PromptInput {...props} />, store);

      // Component should still render without crashing
      expect(screen.getByTestId('icon-button-editPrompt')).toBeInTheDocument();
    });
  });

  describe('Redux State Integration', () => {
    it('should access ui selector values correctly', () => {
      const store = createMockStore({
        promptEditing: {
          open: 'TEST_TOKEN',
          heading: 'Test Heading',
          prompt: 'Test Prompt',
          submitValue: 'Test Submit Value',
          vars: [],
        },
      });

      renderWithProviders(<PromptInput {...defaultProps} />, store);

      // Component should render without errors when accessing selector values
      expect(screen.getByText('Test Label')).toBeInTheDocument();
    });

    it('should handle null promptEditing state', () => {
      const store = createMockStore({
        promptEditing: null,
      });

      renderWithProviders(<PromptInput {...defaultProps} />, store);

      expect(screen.getByText('Test Label')).toBeInTheDocument();
    });
  });

  describe('Accessibility and User Interaction', () => {
    it('should have proper button labels for screen readers', () => {
      const store = createMockStore();
      const props = { ...defaultProps, prompt: 'Modified Prompt' };
      renderWithProviders(<PromptInput {...props} />, store);

      expect(screen.getByTestId('icon-button-editPrompt')).toBeInTheDocument();
      expect(screen.getByTestId('icon-button-ResetDefault')).toBeInTheDocument();
      expect(screen.getByTestId('toggletip-button-Info Label')).toBeInTheDocument();
    });

    it('should render all icons correctly', () => {
      const store = createMockStore();
      const props = { ...defaultProps, prompt: 'Modified Prompt' };
      renderWithProviders(<PromptInput {...props} />, store);

      expect(screen.getByTestId('edit-icon')).toBeInTheDocument();
      expect(screen.getByTestId('reset-icon')).toBeInTheDocument();
      expect(screen.getByTestId('information-icon')).toBeInTheDocument();
    });

    it('should maintain component structure with multiple interactions', () => {
      const store = createMockStore();
      const onChangeMock = vi.fn();
      const resetMock = vi.fn();
      const props = { 
        ...defaultProps, 
        prompt: 'Modified Prompt',
        onChange: onChangeMock,
        reset: resetMock 
      };
      renderWithProviders(<PromptInput {...props} />, store);

      // Click edit button
      fireEvent.click(screen.getByTestId('icon-button-editPrompt'));
      
      // Click reset button
      fireEvent.click(screen.getByTestId('icon-button-ResetDefault'));

      // Verify all elements still exist
      expect(screen.getByText('Test Label')).toBeInTheDocument();
      expect(screen.getByTestId('toggletip')).toBeInTheDocument();
      expect(resetMock).toHaveBeenCalled();
    });
  });
});
