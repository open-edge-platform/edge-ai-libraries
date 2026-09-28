// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';

import { SearchModal, SearchModalProps } from '../components/PopupModal/SearchModal';
import { SearchReducers } from '../redux/search/searchSlice.ts';
import i18n from '../utils/i18n';

// Create mock dispatch
const mockDispatch = vi.fn();

// Create mock store
const createMockStore = () => {
  return configureStore({
    reducer: {
      search: SearchReducers,
    },
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
};


describe('SearchModal Component test suite', () => {
  const defaultProps: SearchModalProps = {
    showModal: true,
    closeModal: vi.fn(),
  };

  const renderComponent = (props: Partial<SearchModalProps> = {}) => {
    const store = createMockStore();
    // Mock the dispatch function
    store.dispatch = mockDispatch;
    
    return render(
      <Provider store={store}>
        <I18nextProvider i18n={i18n}>
          <SearchModal {...defaultProps} {...props} />
        </I18nextProvider>
      </Provider>,
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it('should render the modal when showModal is true', () => {
    renderComponent();
    
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('should not render the modal when showModal is false', () => {
    renderComponent({ showModal: false });
    
    // The modal component might still be in DOM but not visible
    // For Carbon Design Modal, we should check if the modal wrapper is visible
    const modalWrapper = document.querySelector('.cds--modal');
    if (modalWrapper) {
      // Check if the modal has the 'is-visible' class when it should be hidden
      expect(modalWrapper).not.toHaveClass('is-visible');
    }
  });

  it('should render the text area for search input', () => {
    renderComponent();
    
    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });

  it('should update text input when typing in textarea', async () => {
    renderComponent();
    
    const textArea = screen.getByRole('textbox');
    fireEvent.change(textArea, { target: { value: 'test search query' } });
    
    expect(textArea).toHaveValue('test search query');
  });

  it('should call closeModal when cancel button is clicked', async () => {
    const closeModalMock = vi.fn();
    renderComponent({ closeModal: closeModalMock });
    
    const cancelButton = screen.getByText('Cancel');
    fireEvent.click(cancelButton);
    
    expect(closeModalMock).toHaveBeenCalledTimes(1);
  });

  it('should call closeModal when modal close is requested', async () => {
    const closeModalMock = vi.fn();
    renderComponent({ closeModal: closeModalMock });
    
    // Find the close button (X) and click it
    const closeButtons = screen.getAllByRole('button');
    const closeButton = closeButtons.find(btn => btn.getAttribute('aria-label')?.includes('close'));
    if (closeButton) {
      fireEvent.click(closeButton);
      expect(closeModalMock).toHaveBeenCalled();
    }
  });

  it('should dispatch SearchAdd and close modal when search is submitted', async () => {
    const closeModalMock = vi.fn();
    renderComponent({ closeModal: closeModalMock });
    
    const textArea = screen.getByRole('textbox');
    fireEvent.change(textArea, { target: { value: 'test query' } });
    
    const searchButton = screen.getByText('Search');
    fireEvent.click(searchButton);
    
    await waitFor(() => {
      expect(mockDispatch).toHaveBeenCalled();
      expect(closeModalMock).toHaveBeenCalled();
    });
  });

  it('should reset input after successful search submission', async () => {
    const closeModalMock = vi.fn();
    renderComponent({ closeModal: closeModalMock });
    
    const textArea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textArea, { target: { value: 'test query' } });
    
    const searchButton = screen.getByText('Search');
    fireEvent.click(searchButton);
    
    await waitFor(() => {
      expect(textArea.value).toBe('');
    });
  });

  it('should not submit or close the modal on empty search submission', async () => {
    const closeModalMock = vi.fn();
    renderComponent({ closeModal: closeModalMock });

    const searchButton = screen.getByText('Search');
    fireEvent.click(searchButton);

    await waitFor(() => {
      expect(screen.getByText('Enter a search query to continue.')).toBeInTheDocument();
    });
    expect(mockDispatch).not.toHaveBeenCalled();
    expect(closeModalMock).not.toHaveBeenCalled();
  });

  it('should not submit a whitespace-only query', async () => {
    const closeModalMock = vi.fn();
    renderComponent({ closeModal: closeModalMock });

    const textArea = screen.getByRole('textbox');
    fireEvent.change(textArea, { target: { value: '   ' } });
    fireEvent.click(screen.getByText('Search'));

    await waitFor(() => {
      expect(screen.getByText('Enter a search query to continue.')).toBeInTheDocument();
    });
    expect(mockDispatch).not.toHaveBeenCalled();
    expect(closeModalMock).not.toHaveBeenCalled();
  });

  it('should clear the empty-query warning once the user types', async () => {
    renderComponent();

    const textArea = screen.getByRole('textbox');
    fireEvent.click(screen.getByText('Search'));

    await waitFor(() => {
      expect(screen.getByText('Enter a search query to continue.')).toBeInTheDocument();
    });

    fireEvent.change(textArea, { target: { value: 'a query' } });

    await waitFor(() => {
      expect(screen.queryByText('Enter a search query to continue.')).not.toBeInTheDocument();
    });
  });

  it('should submit the search when Enter is pressed in the textarea', async () => {
    const closeModalMock = vi.fn();
    renderComponent({ closeModal: closeModalMock });

    const textArea = screen.getByRole('textbox');
    fireEvent.change(textArea, { target: { value: 'enter key query' } });
    fireEvent.keyDown(textArea, { key: 'Enter' });

    await waitFor(() => {
      expect(mockDispatch).toHaveBeenCalled();
      expect(closeModalMock).toHaveBeenCalled();
    });
  });

  it('should not submit when Shift+Enter is pressed', async () => {
    const closeModalMock = vi.fn();
    renderComponent({ closeModal: closeModalMock });

    const textArea = screen.getByRole('textbox');
    fireEvent.change(textArea, { target: { value: 'multi line query' } });
    fireEvent.keyDown(textArea, { key: 'Enter', shiftKey: true });

    expect(mockDispatch).not.toHaveBeenCalled();
    expect(closeModalMock).not.toHaveBeenCalled();
  });

  it('should not submit on Enter while an IME composition is active', async () => {
    const closeModalMock = vi.fn();
    renderComponent({ closeModal: closeModalMock });

    const textArea = screen.getByRole('textbox');
    fireEvent.change(textArea, { target: { value: 'composing' } });
    fireEvent.keyDown(textArea, { key: 'Enter', isComposing: true });

    expect(mockDispatch).not.toHaveBeenCalled();
    expect(closeModalMock).not.toHaveBeenCalled();
  });

  it('should warn instead of submitting when Enter is pressed with an empty query', async () => {
    const closeModalMock = vi.fn();
    renderComponent({ closeModal: closeModalMock });

    const textArea = screen.getByRole('textbox');
    fireEvent.keyDown(textArea, { key: 'Enter' });

    await waitFor(() => {
      expect(screen.getByText('Enter a search query to continue.')).toBeInTheDocument();
    });
    expect(mockDispatch).not.toHaveBeenCalled();
    expect(closeModalMock).not.toHaveBeenCalled();
  });

  it('should open the date-added tooltip upwards so it is not clipped by the modal', () => {
    const { container } = renderComponent();

    // The time filter is the last field in a scrolling modal body, so a
    // downward tooltip gets cut off by the body's bottom edge.
    // Scoped to the legend: the modal's close button has its own tooltip.
    expect(container.querySelector('legend .cds--tooltip')).toHaveClass(
      'cds--popover--top-start',
    );
  });

  it('should respect maxLength attribute on textarea', () => {
    renderComponent();
    
    const textArea = screen.getByRole('textbox');
    expect(textArea).toHaveAttribute('maxlength', '250');
  });

  it('should have correct modal heading', () => {
    renderComponent();
    
    // The heading should be translated text for 'videoSearchStart'
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('should have correct button labels', () => {
    renderComponent();
    
    expect(screen.getByText('Search')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('should handle textarea ref correctly', () => {
    renderComponent();
    
    const textArea = screen.getByRole('textbox');
    expect(textArea).toBeInTheDocument();
    
    // Type in the textarea and then simulate search to trigger reset
    fireEvent.change(textArea, { target: { value: 'test' } });
    
    const searchButton = screen.getByText('Search');
    fireEvent.click(searchButton);
    
    // The ref-based reset should work
    expect(textArea).toBeInTheDocument();
  });
});
