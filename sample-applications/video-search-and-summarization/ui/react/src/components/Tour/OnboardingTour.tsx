// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useState, useEffect } from 'react';
import styled from 'styled-components';
import { Button } from '@carbon/react';

interface TourStep {
  target: string;
  title: string;
  content: string;
  placement?: 'top' | 'bottom' | 'left' | 'right';
}

interface OnboardingTourProps {
  steps: TourStep[];
  onComplete: () => void;
  isActive: boolean;
}

const Overlay = styled.div`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 9998;
  pointer-events: none;
`;

const Spotlight = styled.div<{ $top: number; $left: number; $width: number; $height: number }>`
  position: fixed;
  top: ${props => props.$top}px;
  left: ${props => props.$left}px;
  width: ${props => props.$width}px;
  height: ${props => props.$height}px;
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.5);
  border-radius: 4px;
  z-index: 9999;
  pointer-events: none;
  transition: all 0.3s ease;
`;

const Tooltip = styled.div<{ $top: number; $left: number; $placement: string }>`
  position: fixed;
  background: white;
  border-radius: 8px;
  padding: 1.5rem;
  max-width: 400px;
  min-width: 320px;
  z-index: 10000;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
  pointer-events: auto;
  box-sizing: border-box;
  
  ${props => {
    switch (props.$placement) {
      case 'bottom':
        return `
          top: ${props.$top}px;
          left: ${props.$left}px;
          transform: translateX(-50%);
        `;
      case 'top':
        return `
          bottom: ${window.innerHeight - props.$top}px;
          left: ${props.$left}px;
          transform: translateX(-50%);
        `;
      case 'right':
        return `
          top: ${props.$top}px;
          left: ${props.$left}px;
          transform: translateY(-50%);
        `;
      case 'left':
        return `
          top: ${props.$top}px;
          right: ${window.innerWidth - props.$left}px;
          transform: translateY(-50%);
        `;
      default:
        return `
          top: ${props.$top}px;
          left: ${props.$left}px;
        `;
    }
  }}
`;

const TooltipTitle = styled.h3`
  margin: 0 0 0.75rem 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-info);
`;

const TooltipContent = styled.p`
  margin: 0 0 1.25rem 0;
  font-size: 1rem;
  line-height: 1.5;
  color: #333;
`;

const TooltipFooter = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  width: 100%;
`;

const StepIndicator = styled.span`
  font-size: 0.875rem;
  color: #666;
  text-align: center;
`;

const ButtonGroup = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: center;
  width: 100%;
  
  button {
    flex: 0 1 auto;
    white-space: nowrap;
  }
`;

export const OnboardingTour: FC<OnboardingTourProps> = ({ steps, onComplete, isActive }) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    if (!isActive || currentStep >= steps.length) return;

    const updateTargetPosition = () => {
      const target = document.querySelector(steps[currentStep].target);
      if (target) {
        const rect = target.getBoundingClientRect();
        setTargetRect(rect);
      }
    };

    updateTargetPosition();
    window.addEventListener('resize', updateTargetPosition);
    window.addEventListener('scroll', updateTargetPosition);

    return () => {
      window.removeEventListener('resize', updateTargetPosition);
      window.removeEventListener('scroll', updateTargetPosition);
    };
  }, [currentStep, steps, isActive]);

  if (!isActive || currentStep >= steps.length || !targetRect) {
    return null;
  }

  const step = steps[currentStep];
  const placement = step.placement || 'bottom';

  const getTooltipPosition = () => {
    const padding = 20;
    const tooltipWidth = 400; // max-width of tooltip
    
    switch (placement) {
      case 'bottom':
        // Calculate position to ensure tooltip doesn't go off-screen
        let leftPos = targetRect.left + targetRect.width / 2;
        
        // Shift left if tooltip would be cropped on the right side
        if (leftPos + tooltipWidth / 2 > window.innerWidth - padding) {
          leftPos = window.innerWidth - tooltipWidth / 2 - padding;
        }
        
        // Shift right if tooltip would be cropped on the left side
        if (leftPos - tooltipWidth / 2 < padding) {
          leftPos = tooltipWidth / 2 + padding;
        }
        
        return {
          top: targetRect.bottom + padding,
          left: leftPos,
        };
      case 'top':
        return {
          top: targetRect.top - padding,
          left: targetRect.left + targetRect.width / 2,
        };
      case 'right':
        return {
          top: targetRect.top + targetRect.height / 2,
          left: targetRect.right + padding,
        };
      case 'left':
        return {
          top: targetRect.top + targetRect.height / 2,
          left: targetRect.left - padding,
        };
      default:
        return {
          top: targetRect.bottom + padding,
          left: targetRect.left + targetRect.width / 2,
        };
    }
  };

  const tooltipPos = getTooltipPosition();

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      onComplete();
    }
  };

  const handleSkip = () => {
    onComplete();
  };

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  return (
    <>
      <Overlay />
      <Spotlight
        $top={targetRect.top}
        $left={targetRect.left}
        $width={targetRect.width}
        $height={targetRect.height}
      />
      <Tooltip $top={tooltipPos.top} $left={tooltipPos.left} $placement={placement}>
        <TooltipTitle>{step.title}</TooltipTitle>
        <TooltipContent>{step.content}</TooltipContent>
        <TooltipFooter>
          <StepIndicator>
            {currentStep + 1} of {steps.length}
          </StepIndicator>
          <ButtonGroup>
            {currentStep > 0 && (
              <Button kind="secondary" size="sm" onClick={handleBack}>
                Back
              </Button>
            )}
            {currentStep === 0 && (
              <Button kind="tertiary" size="sm" onClick={handleSkip}>
                Skip Tour
              </Button>
            )}
            <Button kind="primary" size="sm" onClick={handleNext}>
              {currentStep === steps.length - 1 ? 'Finish' : 'Next'}
            </Button>
          </ButtonGroup>
        </TooltipFooter>
      </Tooltip>
    </>
  );
};

export default OnboardingTour;
