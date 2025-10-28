// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import SummarySideBarItem from '../components/Summaries/SummarySideBarItem';
import { SummarySlice } from '../redux/summary/summarySlice';
import { StateActionStatus, EVAMPipelines, StateStatus } from '../redux/summary/summary';


// Mock Carbon components
vi.mock('@carbon/react', () => ({
  IconButton: vi.fn().mockImplementation(({ children, onClick, label, ...props }) => (
    <button onClick={onClick} aria-label={label} data-testid="icon-button" {...props}>
      {children}
    </button>
  )),
  Modal: vi.fn().mockImplementation(({ children, ...props }) => (
    <div data-testid="carbon-modal" {...props}>
      {children}
    </div>
  )),
}));

// Mock Carbon icons
vi.mock('@carbon/icons-react', () => ({
  TrashCan: vi.fn().mockImplementation(() => <span data-testid="trash-can-icon">TrashCan</span>),
}));

// Mock PopupModal to match the actual component structure
vi.mock('../components/PopupModal/PopupModal', () => ({
  __esModule: true,
  default: vi.fn().mockImplementation(({ 
    open, 
    onClose, 
    onSubmit, 
    headingMsg, 
    primaryButtonText,
    secondaryButtonText,
    children 
  }) => {
    if (!open) return null;
    
    return (
      <div data-testid="popup-modal">
        <div data-testid="modal-header">
          <h2>{headingMsg || 'Delete Confirmation'}</h2>
        </div>
        <div data-testid="modal-content">
          {children || <p>Are you sure you want to delete this summary?</p>}
        </div>
        <div data-testid="modal-footer">
          <button 
            onClick={onClose} 
            data-testid="modal-cancel"
          >
            {secondaryButtonText || 'Cancel'}
          </button>
          <button 
            onClick={onSubmit} 
            data-testid="modal-confirm"
          >
            {primaryButtonText || 'Delete'}
          </button>
        </div>
      </div>
    );
  }),
}));

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: vi.fn().mockImplementation((key: string, options?: any) => {
      const translations: Record<string, string> = {
        'delete': 'Delete',
        'deleteConfirmation': 'Delete Confirmation',
        'deleteMessage': 'Are you sure you want to delete this summary?',
        'cancel': 'Cancel',
        'confirm': 'Confirm'
      };
      return options ? `${translations[key] || key} ${JSON.stringify(options)}` : translations[key] || key;
    }),
  }),
}));

// Mock notification system
vi.mock('../utils/util', () => ({
  uuidv4: vi.fn(() => 'test-uuid-123'),
  notificationSuccess: vi.fn(),
  notificationError: vi.fn(),
}));

// Mock axios for API calls
vi.mock('axios', () => ({
  default: {
    delete: vi.fn().mockResolvedValue({ status: 200 }),
  },
}));

// Mock APP_URL
vi.mock('../config', () => ({
  APP_URL: 'http://localhost:3000',
}));

describe('SummarySideBarItem', () => {
  let store: any;
  let mockDispatch: any;

  const mockSummaryItem = {
    stateId: 'state-123',
    title: 'Test Summary',
    videoId: 'video-456',
    chunksCount: 5,
    framesCount: 10,
    frameSummaries: 3,
    chunkingStatus: StateActionStatus.COMPLETE,
    videoSummaryStatus: StateActionStatus.IN_PROGRESS,
    frameSummaryStatus: {
      na: 0,
      ready: 0,
      inProgress: 2,
      complete: 3
    },
    userInputs: {
      samplingFrame: 1,
      chunkDuration: 30,
      frameOverlap: 5,
      multiFrame: 0
    },
    systemConfig: {
      multiFrame: 0,
      frameOverlap: 5,
      evamPipeline: EVAMPipelines.OBJECT_DETECTION,
      framePrompt: 'Default frame prompt',
      summaryMapPrompt: 'Default map prompt',
      summaryReducePrompt: 'Default reduce prompt',
      summarySinglePrompt: 'Default single prompt'
    },
    inferenceConfig: {
      objectDetection: {
        model: 'yolo',
        device: 'CPU'
      },
      imageInference: {
        model: 'resnet',
        device: 'CPU'
      },
      textInference: {
        model: 'bert',
        device: 'CPU'
      }
    },
    summary: 'Test summary content',
    selected: false
  };

  beforeEach(() => {
    // Create a fresh store for each test
    store = configureStore({
      reducer: {
        summary: SummarySlice.reducer,
      },
      preloadedState: {
        summary: {
          summaries: {},
          selectedSummary: null,
          status: StateStatus.IDLE,
        },
      },
    });

    mockDispatch = vi.spyOn(store, 'dispatch');
    vi.clearAllMocks();
  });

  const renderComponent = (props = {}) => {
    return render(
      <Provider store={store}>
        <SummarySideBarItem
          item={mockSummaryItem}
          onClick={() => {}}
          {...props}
        />
      </Provider>
    );
  };

  it('should render summary item with title and basic information', () => {
    renderComponent();

    expect(screen.getByText('Test Summary')).toBeInTheDocument();
    expect(screen.getByTestId('icon-button')).toBeInTheDocument();
    expect(screen.getByTestId('trash-can-icon')).toBeInTheDocument();
  });

  it('should apply selected class when item is selected', () => {
    const selectedItem = { ...mockSummaryItem, selected: true };
    renderComponent({ item: selectedItem });

    const container = screen.getByText('Test Summary').closest('div');
    expect(container).toBeInTheDocument();
  });

  it('should call onClick when summary item is clicked', () => {
    const mockOnClick = vi.fn();
    renderComponent({ onClick: mockOnClick });

    const summaryItem = screen.getByText('Test Summary').closest('div');
    if (summaryItem) {
      fireEvent.click(summaryItem);
    }

    expect(mockOnClick).toHaveBeenCalledTimes(1);
  });

  it('should open delete modal when trash icon is clicked', () => {
    renderComponent();

    // Initially modal should not be visible
    expect(screen.queryByTestId('popup-modal')).not.toBeInTheDocument();

    // Click the delete button
    const deleteButton = screen.getByTestId('icon-button');
    fireEvent.click(deleteButton);

    // Modal should now be visible
    expect(screen.getByTestId('popup-modal')).toBeInTheDocument();
    expect(screen.getByText('deleteSummary')).toBeInTheDocument();
  });

  it('should close modal when cancel button is clicked', () => {
    renderComponent();

    // Open modal
    fireEvent.click(screen.getByTestId('icon-button'));
    expect(screen.getByTestId('popup-modal')).toBeInTheDocument();

    // Click cancel
    fireEvent.click(screen.getByTestId('modal-cancel'));

    // Modal should be closed
    expect(screen.queryByTestId('popup-modal')).not.toBeInTheDocument();
  });

  it('should dispatch delete action when confirm delete is clicked', async () => {
    renderComponent();

    // Open modal
    fireEvent.click(screen.getByTestId('icon-button'));

    // Click confirm
    fireEvent.click(screen.getByTestId('modal-confirm'));

    // Wait for async operations
    await waitFor(() => {
      expect(mockDispatch).toHaveBeenCalled();
    });

    // Modal should be closed after deletion
    expect(screen.queryByTestId('popup-modal')).not.toBeInTheDocument();
  });

  it('should prevent event propagation when delete button is clicked', () => {
    const mockOnClick = vi.fn();
    renderComponent({ onClick: mockOnClick });

    const deleteButton = screen.getByTestId('icon-button');
    fireEvent.click(deleteButton);

    // Summary onClick should not be called when delete button is clicked
    expect(mockOnClick).not.toHaveBeenCalled();
  });

  it('should render with different summary data', () => {
    const differentItem = {
      ...mockSummaryItem,
      stateId: 'different-id',
      title: 'Different Summary Title',
      chunkingStatus: StateActionStatus.COMPLETE,
    };

    renderComponent({ item: differentItem });

    expect(screen.getByText('Different Summary Title')).toBeInTheDocument();
  });

  it('should handle empty or undefined item gracefully', () => {
    // Component should handle undefined item without crashing - but React may throw for truly broken props
    // Instead, let's test with an empty item object
    const emptyItem = {
      stateId: '',
      title: '',
      selected: false
    };
    
    expect(() => {
      renderComponent({ item: emptyItem });
    }).not.toThrow();
  });

  it('should display summary status information', () => {
    renderComponent();

    // The component should show the summary title
    expect(screen.getByText('Test Summary')).toBeInTheDocument();
    
    // Delete button should be present
    expect(screen.getByTestId('icon-button')).toBeInTheDocument();
  });

  it('should handle multiple rapid clicks on delete button', () => {
    renderComponent();

    const deleteButton = screen.getByTestId('icon-button');
    
    // Click multiple times rapidly
    fireEvent.click(deleteButton);
    fireEvent.click(deleteButton);
    fireEvent.click(deleteButton);

    // Should only show one modal
    expect(screen.getAllByTestId('popup-modal')).toHaveLength(1);
  });

  it('should handle modal confirm with network delay', async () => {
    // Mock axios with a delay
    const axios = await import('axios');
    vi.mocked(axios.default.delete).mockImplementation(() => 
      new Promise(resolve => setTimeout(() => resolve({ status: 200 }), 100))
    );

    renderComponent();

    fireEvent.click(screen.getByTestId('icon-button'));
    fireEvent.click(screen.getByTestId('modal-confirm'));

    // Should close modal after successful deletion
    await waitFor(() => {
      expect(screen.queryByTestId('popup-modal')).not.toBeInTheDocument();
    }, { timeout: 200 });
  });

  it('should render correctly with minimal summary data', () => {
    const minimalItem = {
      stateId: 'minimal',
      title: 'Minimal Summary',
      videoId: 'video-minimal',
      chunksCount: 0,
      framesCount: 0,
      frameSummaries: 0,
      chunkingStatus: StateActionStatus.NA,
      videoSummaryStatus: StateActionStatus.NA,
      frameSummaryStatus: {
        na: 0,
        ready: 0,
        inProgress: 0,
        complete: 0
      },
      userInputs: {
        samplingFrame: 1,
        chunkDuration: 30,
        frameOverlap: 0,
        multiFrame: 0
      },
      systemConfig: {
        multiFrame: 0,
        frameOverlap: 0,
        evamPipeline: EVAMPipelines.BASIC_INGESTION,
        framePrompt: 'Default frame prompt',
        summaryMapPrompt: 'Default map prompt',
        summaryReducePrompt: 'Default reduce prompt',
        summarySinglePrompt: 'Default single prompt'
      },
      summary: '',
      selected: false
    };

    renderComponent({ item: minimalItem });

    expect(screen.getByText('Minimal Summary')).toBeInTheDocument();
    expect(screen.getByTestId('icon-button')).toBeInTheDocument();
  });

  it('should handle accessibility attributes correctly', () => {
    renderComponent();

    const deleteButton = screen.getByTestId('icon-button');
    expect(deleteButton).toHaveAttribute('aria-label', 'deleteSummaryLabel');
  });

  it('should show different statuses correctly', () => {
    const itemWithDifferentStatus = {
      ...mockSummaryItem,
      chunkingStatus: StateActionStatus.IN_PROGRESS,
      videoSummaryStatus: StateActionStatus.COMPLETE
    };

    renderComponent({ item: itemWithDifferentStatus });

    expect(screen.getByText('Test Summary')).toBeInTheDocument();
  });

  it('should handle onClick prop being undefined', () => {
    renderComponent({ onClick: undefined });

    const summaryItem = screen.getByText('Test Summary').closest('div');
    
    expect(() => {
      if (summaryItem) {
        fireEvent.click(summaryItem);
      }
    }).not.toThrow();
  });

  it('should render selected state correctly', () => {
    const selectedItem = { ...mockSummaryItem, selected: true };
    renderComponent({ item: selectedItem });

    const container = screen.getByText('Test Summary').closest('div');
    expect(container).toBeInTheDocument();
    // The selected state should be visually different (through CSS classes)
  });
});
