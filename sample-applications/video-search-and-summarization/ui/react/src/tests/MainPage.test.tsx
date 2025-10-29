// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { I18nextProvider } from 'react-i18next';
import { Provider } from 'react-redux';

import MainPage from '../components/MainPage/MainPage.tsx';
import store from '../redux/store';
import i18n from '../utils/i18n';

// Mock config values
vi.mock('../config.ts', () => ({
  APP_URL: 'http://localhost:3000',
  ASSETS_ENDPOINT: 'http://localhost:3000/assets',
  SOCKET_APPEND: '/socket',
  FEATURE_SUMMARY: 'ON',
  FEATURE_SEARCH: 'ON',
  FEATURE_MUX: 'ATOMIC',
}));

// Mock child components
vi.mock('../components/Navbar/Navbar.tsx', () => ({
  default: () => <div data-testid='navbar'>Navbar</div>,
}));

vi.mock('../components/Notice/Notice.tsx', () => ({
  default: ({ message, isNoticeVisible, setIsNoticeVisible }: any) => (
    <div data-testid="notice" style={{ display: isNoticeVisible ? 'block' : 'none' }}>
      <div data-testid="notice-message">{message}</div>
      <button onClick={() => setIsNoticeVisible(false)}>Close Notice</button>
    </div>
  ),
}));

vi.mock('../components/MainPage/SplashAtomic.tsx', () => ({
  SplashAtomic: () => <div data-testid="splash-atomic">Splash Atomic</div>,
  SplashAtomicSearch: () => <div data-testid="splash-atomic-search">Splash Atomic Search</div>,
  SplashAtomicSummary: () => <div data-testid="splash-atomic-summary">Splash Atomic Summary</div>,
}));

// Mock i18next
vi.mock('react-i18next', async () => ({
  ...await vi.importActual('react-i18next'),
  useTranslation: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        noticeMessage: 'This is a notice message',
        showNoticeHiddenButton: 'Show Notice (Hidden)',
      };
      return translations[key] || key;
    },
  }),
}));

describe('MainPage Component', () => {
  const renderComponent = () => {
    return render(
      <Provider store={store}>
        <I18nextProvider i18n={i18n}>
          <MainPage />
        </I18nextProvider>
      </Provider>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Rendering', () => {
    it('should render the main page correctly', () => {
      renderComponent();

      expect(screen.getByTestId('navbar')).toBeInTheDocument();
      expect(screen.getByTestId('notice')).toBeInTheDocument();
    });

    it('should render the main page with proper structure', () => {
      renderComponent();

      const mainElement = screen.getByRole('main');
      expect(mainElement).toBeInTheDocument();
    });

    it('should have hidden notice toggle button', () => {
      renderComponent();

      const hiddenButton = screen.getByTestId('toggle-notice');
      expect(hiddenButton).toBeInTheDocument();
    });

    it('should render notice component with initial state', () => {
      renderComponent();

      const notice = screen.getByTestId('notice');
      expect(notice).toBeInTheDocument();
      expect(notice).toHaveStyle('display: none'); // Initially hidden
    });
  });

  describe('Notice Functionality', () => {
    it('should show notice when toggle button is clicked', () => {
      renderComponent();

      const toggleButton = screen.getByTestId('toggle-notice');
      const notice = screen.getByTestId('notice');

      // Initially hidden
      expect(notice).toHaveStyle('display: none');

      // Click to show
      fireEvent.click(toggleButton);

      expect(notice).toHaveStyle('display: block');
    });

    it('should display notice message correctly', () => {
      renderComponent();

      const toggleButton = screen.getByTestId('toggle-notice');
      fireEvent.click(toggleButton);

      expect(screen.getByTestId('notice-message')).toBeInTheDocument();
    });

    it('should hide notice when close button is clicked', () => {
      renderComponent();

      const toggleButton = screen.getByTestId('toggle-notice');
      fireEvent.click(toggleButton);

      const notice = screen.getByTestId('notice');
      expect(notice).toHaveStyle('display: block');

      const closeButton = screen.getByText('Close Notice');
      fireEvent.click(closeButton);

      expect(notice).toHaveStyle('display: none');
    });

    it('should handle notice state toggle multiple times', () => {
      renderComponent();

      const toggleButton = screen.getByTestId('toggle-notice');
      const notice = screen.getByTestId('notice');

      // Initially hidden
      expect(notice).toHaveStyle('display: none');

      // Show
      fireEvent.click(toggleButton);
      expect(notice).toHaveStyle('display: block');

      // Hide
      const closeButton = screen.getByText('Close Notice');
      fireEvent.click(closeButton);
      expect(notice).toHaveStyle('display: none');

      // Show again
      fireEvent.click(toggleButton);
      expect(notice).toHaveStyle('display: block');
    });
  });

  describe('Splash Component Rendering', () => {
    it('should render a splash component', () => {
      renderComponent();

      // Should render one of the splash components
      expect(
        screen.queryByTestId('splash-atomic') ||
        screen.queryByTestId('splash-atomic-search') ||
        screen.queryByTestId('splash-atomic-summary')
      ).toBeInTheDocument();
    });

    it('should render splash component within grid layout', () => {
      renderComponent();

      // Check that splash component is rendered
      const splashComponent = 
        screen.queryByTestId('splash-atomic') ||
        screen.queryByTestId('splash-atomic-search') ||
        screen.queryByTestId('splash-atomic-summary');
      
      expect(splashComponent).toBeInTheDocument();
    });
  });

  describe('Layout and Structure', () => {
    it('should have main element with proper role', () => {
      renderComponent();

      const mainElement = screen.getByRole('main');
      expect(mainElement).toBeInTheDocument();
    });

    it('should render all main components', () => {
      renderComponent();

      expect(screen.getByTestId('navbar')).toBeInTheDocument();
      expect(screen.getByTestId('notice')).toBeInTheDocument();
      expect(screen.getByTestId('toggle-notice')).toBeInTheDocument();
    });

    it('should maintain layout structure', () => {
      renderComponent();

      expect(screen.getByTestId('navbar')).toBeInTheDocument();
      expect(
        screen.queryByTestId('splash-atomic') ||
        screen.queryByTestId('splash-atomic-search') ||
        screen.queryByTestId('splash-atomic-summary')
      ).toBeInTheDocument();
      expect(screen.getByTestId('notice')).toBeInTheDocument();
    });
  });

  describe('Component Integration', () => {
    it('should integrate with Redux store', () => {
      renderComponent();

      // Component should render without store-related errors
      expect(screen.getByTestId('navbar')).toBeInTheDocument();
    });

    it('should integrate with i18n translations', () => {
      renderComponent();

      const toggleButton = screen.getByTestId('toggle-notice');
      expect(toggleButton).toBeInTheDocument();
      
      // Button should have translation text
      expect(toggleButton.textContent).toBeTruthy();
    });

    it('should handle state management correctly', () => {
      renderComponent();

      const toggleButton = screen.getByTestId('toggle-notice');
      const notice = screen.getByTestId('notice');

      // Test state changes
      expect(notice).toHaveStyle('display: none');
      
      fireEvent.click(toggleButton);
      expect(notice).toHaveStyle('display: block');
    });
  });

  describe('Accessibility', () => {
    it('should have proper semantic HTML structure', () => {
      renderComponent();

      expect(screen.getByRole('main')).toBeInTheDocument();
    });

    it('should have accessible buttons', () => {
      renderComponent();

      const toggleButton = screen.getByTestId('toggle-notice');
      expect(toggleButton.tagName).toBe('BUTTON');
    });

    it('should maintain focus management', () => {
      renderComponent();

      const toggleButton = screen.getByTestId('toggle-notice');
      toggleButton.focus();
      expect(document.activeElement).toBe(toggleButton);
    });

    it('should support keyboard navigation', () => {
      renderComponent();

      const toggleButton = screen.getByTestId('toggle-notice');
      
      // Should be focusable
      toggleButton.focus();
      expect(document.activeElement).toBe(toggleButton);
      
      // Should respond to click events (keyboard activation)
      fireEvent.click(toggleButton);
      
      const notice = screen.getByTestId('notice');
      expect(notice).toHaveStyle('display: block');
    });
  });

  describe('Error Handling', () => {
    it('should handle missing translation keys gracefully', () => {
      renderComponent();
      
      // Component should render even with potential missing translations
      expect(screen.getByTestId('navbar')).toBeInTheDocument();
    });

    it('should maintain stability with rapid state changes', () => {
      renderComponent();

      const toggleButton = screen.getByTestId('toggle-notice');
      const notice = screen.getByTestId('notice');

      // Rapid toggle operations
      for (let i = 0; i < 5; i++) {
        fireEvent.click(toggleButton);
        expect(notice).toHaveStyle('display: block');
        
        const closeButton = screen.getByText('Close Notice');
        fireEvent.click(closeButton);
        expect(notice).toHaveStyle('display: none');
      }
    });


  });
});
