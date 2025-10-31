// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import OnboardingTour from '../components/Tour/OnboardingTour';

// Mock Carbon React components
vi.mock('@carbon/react', () => ({
  Button: ({ children, onClick, kind, size }: any) => (
    <button 
      onClick={onClick} 
      data-kind={kind} 
      data-size={size}
      className="carbon-button"
    >
      {children}
    </button>
  ),
}));

const mockSteps = [
  {
    target: '#step1',
    title: 'Step 1 Title',
    content: 'This is the content for step 1',
    placement: 'bottom' as const,
  },
  {
    target: '#step2',
    title: 'Step 2 Title',
    content: 'This is the content for step 2',
    placement: 'top' as const,
  },
  {
    target: '#step3',
    title: 'Step 3 Title',
    content: 'This is the content for step 3',
    placement: 'right' as const,
  },
];

const mockElement = {
  getBoundingClientRect: () => ({
    top: 100,
    left: 200,
    bottom: 150,
    right: 300,
    width: 100,
    height: 50,
    x: 200,
    y: 100,
    toJSON: () => {},
  }),
};

describe('OnboardingTour Component', () => {
  const mockOnComplete = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock querySelector to return our mock element
    vi.spyOn(document, 'querySelector').mockImplementation((selector) => {
      if (selector === '#step1' || selector === '#step2' || selector === '#step3') {
        return mockElement as any;
      }
      return null;
    });

    // Mock window dimensions
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 1024,
    });
    Object.defineProperty(window, 'innerHeight', {
      writable: true,
      configurable: true,
      value: 768,
    });

    // Mock event listeners
    vi.spyOn(window, 'addEventListener').mockImplementation(vi.fn());
    vi.spyOn(window, 'removeEventListener').mockImplementation(vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Rendering States', () => {
    it('should not render when isActive is false', () => {
      render(
        <OnboardingTour
          steps={mockSteps}
          onComplete={mockOnComplete}
          isActive={false}
        />
      );

      expect(screen.queryByText('Step 1 Title')).not.toBeInTheDocument();
    });

    it('should not render when no steps provided', () => {
      render(
        <OnboardingTour
          steps={[]}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(screen.queryByText('Skip Tour')).not.toBeInTheDocument();
    });

    it('should not render when target element not found', () => {
      vi.spyOn(document, 'querySelector').mockReturnValue(null);

      render(
        <OnboardingTour
          steps={mockSteps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(screen.queryByText('Step 1 Title')).not.toBeInTheDocument();
    });

    it('should render first step when active and target exists', () => {
      render(
        <OnboardingTour
          steps={mockSteps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(screen.getByText('Step 1 Title')).toBeInTheDocument();
      expect(screen.getByText('This is the content for step 1')).toBeInTheDocument();
      expect(screen.getByText('1 of 3')).toBeInTheDocument();
    });
  });

  describe('Navigation Controls', () => {
    it('should show Skip Tour button on first step', () => {
      render(
        <OnboardingTour
          steps={mockSteps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(screen.getByText('Skip Tour')).toBeInTheDocument();
      expect(screen.getByText('Next')).toBeInTheDocument();
      expect(screen.queryByText('Back')).not.toBeInTheDocument();
    });

    it('should show Back button on subsequent steps', () => {
      render(
        <OnboardingTour
          steps={mockSteps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      // Navigate to second step
      fireEvent.click(screen.getByText('Next'));

      expect(screen.getByText('Back')).toBeInTheDocument();
      expect(screen.getByText('Next')).toBeInTheDocument();
      expect(screen.queryByText('Skip Tour')).not.toBeInTheDocument();
    });

    it('should show Finish button on last step', () => {
      render(
        <OnboardingTour
          steps={mockSteps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      // Navigate to last step
      fireEvent.click(screen.getByText('Next'));
      fireEvent.click(screen.getByText('Next'));

      expect(screen.getByText('Finish')).toBeInTheDocument();
      expect(screen.queryByText('Next')).not.toBeInTheDocument();
    });
  });

  describe('Step Navigation', () => {
    it('should advance to next step when Next button clicked', () => {
      render(
        <OnboardingTour
          steps={mockSteps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(screen.getByText('Step 1 Title')).toBeInTheDocument();

      fireEvent.click(screen.getByText('Next'));

      expect(screen.getByText('Step 2 Title')).toBeInTheDocument();
      expect(screen.getByText('This is the content for step 2')).toBeInTheDocument();
      expect(screen.getByText('2 of 3')).toBeInTheDocument();
    });

    it('should go back to previous step when Back button clicked', () => {
      render(
        <OnboardingTour
          steps={mockSteps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      // Go to step 2
      fireEvent.click(screen.getByText('Next'));
      expect(screen.getByText('Step 2 Title')).toBeInTheDocument();

      // Go back to step 1
      fireEvent.click(screen.getByText('Back'));
      expect(screen.getByText('Step 1 Title')).toBeInTheDocument();
    });

    it('should call onComplete when Skip Tour clicked', () => {
      render(
        <OnboardingTour
          steps={mockSteps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      fireEvent.click(screen.getByText('Skip Tour'));

      expect(mockOnComplete).toHaveBeenCalledTimes(1);
    });

    it('should call onComplete when Finish clicked on last step', () => {
      render(
        <OnboardingTour
          steps={mockSteps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      // Navigate to last step
      fireEvent.click(screen.getByText('Next'));
      fireEvent.click(screen.getByText('Next'));
      fireEvent.click(screen.getByText('Finish'));

      expect(mockOnComplete).toHaveBeenCalledTimes(1);
    });
  });

  describe('Tooltip Positioning', () => {
    it('should handle bottom placement', () => {
      const steps = [
        {
          target: '#step1',
          title: 'Bottom Placement',
          content: 'Test content',
          placement: 'bottom' as const,
        },
      ];

      render(
        <OnboardingTour
          steps={steps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(screen.getByText('Bottom Placement')).toBeInTheDocument();
    });

    it('should handle top placement', () => {
      const steps = [
        {
          target: '#step1',
          title: 'Top Placement',
          content: 'Test content',
          placement: 'top' as const,
        },
      ];

      render(
        <OnboardingTour
          steps={steps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(screen.getByText('Top Placement')).toBeInTheDocument();
    });

    it('should handle right placement', () => {
      const steps = [
        {
          target: '#step1',
          title: 'Right Placement',
          content: 'Test content',
          placement: 'right' as const,
        },
      ];

      render(
        <OnboardingTour
          steps={steps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(screen.getByText('Right Placement')).toBeInTheDocument();
    });

    it('should handle left placement', () => {
      const steps = [
        {
          target: '#step1',
          title: 'Left Placement',
          content: 'Test content',
          placement: 'left' as const,
        },
      ];

      render(
        <OnboardingTour
          steps={steps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(screen.getByText('Left Placement')).toBeInTheDocument();
    });

    it('should default to bottom placement when placement not specified', () => {
      const steps = [
        {
          target: '#step1',
          title: 'Default Placement',
          content: 'Test content',
          // no placement specified
        },
      ];

      render(
        <OnboardingTour
          steps={steps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(screen.getByText('Default Placement')).toBeInTheDocument();
    });
  });

  describe('Event Listeners', () => {
    it('should add and remove resize and scroll event listeners', () => {
      const { unmount } = render(
        <OnboardingTour
          steps={mockSteps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(window.addEventListener).toHaveBeenCalledWith('resize', expect.any(Function));
      expect(window.addEventListener).toHaveBeenCalledWith('scroll', expect.any(Function));

      unmount();

      expect(window.removeEventListener).toHaveBeenCalledWith('resize', expect.any(Function));
      expect(window.removeEventListener).toHaveBeenCalledWith('scroll', expect.any(Function));
    });

    it('should update target position when window resizes', () => {
      render(
        <OnboardingTour
          steps={mockSteps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(screen.getByText('Step 1 Title')).toBeInTheDocument();

      // Simulate resize event
      act(() => {
        const resizeHandler = (window.addEventListener as any).mock.calls.find(
          (call: any) => call[0] === 'resize'
        )?.[1];
        if (resizeHandler) {
          resizeHandler();
        }
      });

      expect(screen.getByText('Step 1 Title')).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    it('should handle step with very long content', () => {
      const longContentSteps = [
        {
          target: '#step1',
          title: 'Very Long Title That Should Still Be Handled Properly',
          content: 'This is a very long content that should test how the tooltip handles extensive text. '.repeat(10),
          placement: 'bottom' as const,
        },
      ];

      render(
        <OnboardingTour
          steps={longContentSteps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(screen.getByText('Very Long Title That Should Still Be Handled Properly')).toBeInTheDocument();
    });

    it('should handle single step tour', () => {
      const singleStep = [
        {
          target: '#step1',
          title: 'Single Step',
          content: 'This is a single step tour',
          placement: 'bottom' as const,
        },
      ];

      render(
        <OnboardingTour
          steps={singleStep}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(screen.getByText('1 of 1')).toBeInTheDocument();
      expect(screen.getByText('Finish')).toBeInTheDocument();
      expect(screen.queryByText('Next')).not.toBeInTheDocument();
    });

    it('should handle when Back button clicked on first step (should not go back)', () => {
      render(
        <OnboardingTour
          steps={mockSteps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(screen.getByText('Step 1 Title')).toBeInTheDocument();
      // Back button should not be visible on first step
      expect(screen.queryByText('Back')).not.toBeInTheDocument();
    });

    it('should handle tooltip position adjustment for screen boundaries', () => {
      // Mock narrow window
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 500,
      });

      render(
        <OnboardingTour
          steps={mockSteps}
          onComplete={mockOnComplete}
          isActive={true}
        />
      );

      expect(screen.getByText('Step 1 Title')).toBeInTheDocument();
    });
  });
});