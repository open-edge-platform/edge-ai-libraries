// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Provider } from 'react-redux';
import { I18nextProvider } from 'react-i18next';
import { configureStore } from '@reduxjs/toolkit';
import i18next from 'i18next';
import Navbar from '../components/Navbar/Navbar';
import { SummarySlice } from '../redux/summary/summarySlice';
import { VideoSlice } from '../redux/video/videoSlice';
import { UISlice } from '../redux/ui/ui.slice';
import { SearchSlice } from '../redux/search/searchSlice';

// Create mock i18n instance
const i18n = i18next.createInstance({
  lng: 'en',
  fallbackLng: 'en',
  resources: {
    en: {
      translation: {
        VSSBrand: 'VSSBrand',
        VSearchBrand: 'VSearchBrand', 
        VSummBrand: 'VSummBrand',
        CreateVideoEmbedding: 'CreateVideoEmbedding',
        SummarizeVideo: 'SummarizeVideo',
        SearchVideo: 'SearchVideo',
        VideoUpload: 'VideoUpload'
      }
    }
  },
  interpolation: { escapeValue: false }
}, () => {});

// Mock Carbon components
vi.mock('@carbon/react', () => ({
  Button: ({ children, onClick, kind, disabled }: any) => (
    <button data-testid="carbon-button" onClick={onClick} data-kind={kind} disabled={disabled}>
      {children}
    </button>
  ),
  Modal: ({ children, open }: any) => (
    <div data-testid="carbon-modal" data-open={open}>
      {children}
    </div>
  ),
  IconButton: ({ children, onClick, label }: any) => (
    <button data-testid="carbon-icon-button" onClick={onClick} aria-label={label}>
      {children}
    </button>
  ),
  TextInput: ({ children, ...props }: any) => (
    <input data-testid="text-input" {...props}>
      {children}
    </input>
  ),
  NumberInput: ({ children, ...props }: any) => (
    <input data-testid="number-input" type="number" {...props}>
      {children}
    </input>
  ),
  Select: ({ children, ...props }: any) => (
    <select data-testid="carbon-select" {...props}>
      {children}
    </select>
  ),
  Accordion: ({ children }: any) => <div data-testid="accordion">{children}</div>,
  AccordionItem: ({ children, title }: any) => (
    <div data-testid="accordion-item" data-title={title}>
      {children}
    </div>
  ),
  Toggletip: ({ children, autoAlign }: any) => (
    <div data-testid="toggletip" data-auto-align={autoAlign}>
      {children}
    </div>
  ),
  ToggletipButton: ({ children }: any) => (
    <button data-testid="toggletip-button">
      {children}
    </button>
  ),
  ToggletipContent: ({ children }: any) => (
    <div data-testid="toggletip-content">
      {children}
    </div>
  ),
}));

// Mock @carbon/icons-react
vi.mock('@carbon/icons-react', () => ({
  Video: () => <div data-testid="video-icon">Video Icon</div>,
  Search: () => <div data-testid="search-icon">Search Icon</div>,
  Close: () => <div data-testid="close-icon">Close Icon</div>,
}));

// Mock Carbon icons
vi.mock('@carbon/icons-react', () => ({
  Video: () => <div data-testid="video-icon">Video Icon</div>,
  Information: () => <div data-testid="information-icon">Information Icon</div>,
  Close: () => <div data-testid="close-icon">Close Icon</div>,
  Search: () => <div data-testid="search-icon">Search Icon</div>,
}));

// Mock components
vi.mock('../Drawer/Drawer.tsx', () => ({
  default: ({ isOpen, close, title, children }: any) => (
    <div data-testid="drawer" data-open={isOpen}>
      <div data-testid="drawer-title">{title}</div>
      <div data-testid="drawer-content">{children}</div>
      <button onClick={close} data-testid="drawer-close">Close</button>
    </div>
  ),
}));

vi.mock('../Drawer/VideoUpload.tsx', () => ({
  default: ({ closeDrawer, isOpen }: any) => (
    <div data-testid="video-upload" data-open={isOpen}>
      <button onClick={closeDrawer} data-testid="video-upload-close">Close Upload</button>
    </div>
  ),
}));

vi.mock('../Drawer/VideoUploadSearch.tsx', () => ({
  VideoUploadSearch: ({ closeDrawer, isOpen }: any) => (
    <div data-testid="video-upload-search" data-open={isOpen}>
      <button onClick={closeDrawer} data-testid="video-upload-search-close">Close Upload Search</button>
    </div>
  ),
}));

vi.mock('../Modals/PromptInputModal.tsx', () => ({
  default: () => <div data-testid="prompt-input-modal">Prompt Input Modal</div>,
}));

vi.mock('../PopupModal/SearchModal.tsx', () => ({
  SearchModal: ({ showModal, closeModal }: any) => (
    showModal ? (
      <div data-testid="search-modal">
        <button onClick={closeModal} data-testid="search-modal-close">Close Search</button>
      </div>
    ) : null
  ),
}));

// Mock hooks
vi.mock('../../hooks/useDisclosure.ts', () => ({
  useDisclosure: () => [false, { open: vi.fn(), close: vi.fn() }],
}));

// Mock config constants
vi.mock('../../config.ts', () => ({
  FEATURE_SEARCH: 'ON',
  FEATURE_SUMMARY: 'ON',
}));

// Mock constants
vi.mock('../../utils/constant.ts', () => ({
  FEATURE_STATE: {
    ON: 'ON',
    OFF: 'OFF',
  },
}));

// Mock video slice action
vi.mock('../../redux/video/videoSlice.ts', () => ({
  ...vi.importActual('../../redux/video/videoSlice.ts'),
  videosLoad: vi.fn(() => ({ type: 'videos/load' })),
}));

const createTestStore = () => {
  return configureStore({
    reducer: {
      summary: SummarySlice.reducer,
      videos: VideoSlice.reducer,
      ui: UISlice.reducer,
      search: SearchSlice.reducer,
    },
  });
};

const renderWithProviders = (store = createTestStore()) => {
  return render(
    <Provider store={store}>
      <I18nextProvider i18n={i18n}>
        <Navbar />
      </I18nextProvider>
    </Provider>
  );
};

describe('Navbar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render without crashing', () => {
    expect(() => renderWithProviders()).not.toThrow();
  });

  it('should have proper component structure with buttons', () => {
    renderWithProviders();
    
    const buttons = screen.getAllByTestId('carbon-button');
    expect(buttons.length).toBeGreaterThan(0);
  });

  it('should render video icon', () => {
    renderWithProviders();
    expect(screen.getByTestId('video-icon')).toBeInTheDocument();
  });

  it('should render search modal container', () => {
    renderWithProviders();
    // Search modal should not be visible initially but component should handle it
    expect(screen.queryByTestId('search-modal')).not.toBeInTheDocument();
  });
});
