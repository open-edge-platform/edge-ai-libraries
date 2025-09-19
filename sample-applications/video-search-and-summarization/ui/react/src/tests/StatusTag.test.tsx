// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';
import '@testing-library/jest-dom';
import StatusTag, { StatusIndicator, CountStatusEmp, getStatusByPriority } from '../components/Summaries/StatusTag';
import { StateActionStatus } from '../redux/summary/summary';

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        naTag: 'Not Available',
        readyTag: 'Ready',
        progressTag: 'In Progress',
        completeTag: 'Complete',
      };
      return translations[key] || key;
    },
  }),
}));

describe('StatusTag Component', () => {
  describe('StatusTag', () => {
    it('should render correctly with basic props', () => {
      render(<StatusTag label="Test Status" action={StateActionStatus.COMPLETE} />);
      
      expect(screen.getByText(/Test Status/)).toBeInTheDocument();
      expect(screen.getByText(/Complete/)).toBeInTheDocument();
    });

    it('should render with count', () => {
      render(<StatusTag label="Processing" action={StateActionStatus.IN_PROGRESS} count={5} />);
      
      expect(screen.getByText(/Processing/)).toBeInTheDocument();
      expect(screen.getByText(/In Progress/)).toBeInTheDocument();
      expect(screen.getByText(/5/)).toBeInTheDocument();
    });

    it('should render with count and total', () => {
      render(<StatusTag label="Processing" action={StateActionStatus.IN_PROGRESS} count={3} total={10} />);
      
      expect(screen.getByText(/Processing/)).toBeInTheDocument();
      expect(screen.getByText(/In Progress/)).toBeInTheDocument();
      expect(screen.getByText(/3/)).toBeInTheDocument();
      expect(screen.getByText(/10/)).toBeInTheDocument();
    });

    it('should not render when action is not provided', () => {
      const { container } = render(<StatusTag label="Test Status" />);
      
      expect(container.firstChild).toBeNull();
    });

    it('should render with different status types', () => {
      const statuses = [
        StateActionStatus.NA,
        StateActionStatus.READY,
        StateActionStatus.IN_PROGRESS,
        StateActionStatus.COMPLETE,
      ];

      statuses.forEach((status) => {
        const { container } = render(<StatusTag label="Test" action={status} />);
        expect(container.firstChild).not.toBeNull();
      });
    });
  });

  describe('StatusIndicator', () => {
    it('should render correctly with action', () => {
      const { container } = render(<StatusIndicator label="Test Indicator" action={StateActionStatus.COMPLETE} />);
      
      expect(container.firstChild).not.toBeNull();
    });

    it('should render with default NA status when no action provided', () => {
      const { container } = render(<StatusIndicator label="Test Indicator" />);
      
      expect(container.firstChild).not.toBeNull();
    });
  });

  describe('CountStatusEmp', () => {
    it('should render tags for each status count', () => {
      const status = {
        [StateActionStatus.NA]: 2,
        [StateActionStatus.READY]: 1,
        [StateActionStatus.IN_PROGRESS]: 3,
        [StateActionStatus.COMPLETE]: 5,
      };

      render(<CountStatusEmp status={status} label="Test Status" />);
      
      expect(screen.getByText(/2/)).toBeInTheDocument();
      expect(screen.getByText(/1/)).toBeInTheDocument();
      expect(screen.getByText(/3/)).toBeInTheDocument();
      expect(screen.getByText(/5/)).toBeInTheDocument();
    });

    it('should not render tags for zero counts', () => {
      const status = {
        [StateActionStatus.NA]: 0,
        [StateActionStatus.READY]: 0,
        [StateActionStatus.IN_PROGRESS]: 2,
        [StateActionStatus.COMPLETE]: 0,
      };

      render(<CountStatusEmp status={status} label="Test Status" />);
      
      expect(screen.getByText(/2/)).toBeInTheDocument();
    });

    it('should render with empty status counts', () => {
      const status = {
        [StateActionStatus.NA]: 0,
        [StateActionStatus.READY]: 0,
        [StateActionStatus.IN_PROGRESS]: 0,
        [StateActionStatus.COMPLETE]: 0,
      };

      const { container } = render(<CountStatusEmp status={status} label="Test Status" />);
      
      // Component should render nothing when all counts are 0
      expect(container.firstChild).toBeNull();
    });
  });

  describe('getStatusByPriority', () => {
    it('should return the lowest priority status with count > 0', () => {
      const counts = {
        [StateActionStatus.NA]: 1,
        [StateActionStatus.READY]: 2,
        [StateActionStatus.IN_PROGRESS]: 1,
        [StateActionStatus.COMPLETE]: 3,
      };

      // Function returns last status in priority order that has count > 0
      const result = getStatusByPriority(counts);
      expect(result).toBe(StateActionStatus.NA);
    });

    it('should return READY when NA has no count', () => {
      const counts = {
        [StateActionStatus.NA]: 0,
        [StateActionStatus.READY]: 2,
        [StateActionStatus.IN_PROGRESS]: 1,
        [StateActionStatus.COMPLETE]: 3,
      };

      const result = getStatusByPriority(counts);
      expect(result).toBe(StateActionStatus.READY);
    });

    it('should return COMPLETE when READY and NA have no count', () => {
      const counts = {
        [StateActionStatus.NA]: 0,
        [StateActionStatus.READY]: 0,
        [StateActionStatus.IN_PROGRESS]: 1,
        [StateActionStatus.COMPLETE]: 3,
      };

      const result = getStatusByPriority(counts);
      expect(result).toBe(StateActionStatus.COMPLETE);
    });

    it('should return IN_PROGRESS when only IN_PROGRESS has count', () => {
      const counts = {
        [StateActionStatus.NA]: 0,
        [StateActionStatus.READY]: 0,
        [StateActionStatus.IN_PROGRESS]: 1,
        [StateActionStatus.COMPLETE]: 0,
      };

      const result = getStatusByPriority(counts);
      expect(result).toBe(StateActionStatus.IN_PROGRESS);
    });

    it('should return NA when all counts are zero (default)', () => {
      const counts = {
        [StateActionStatus.NA]: 0,
        [StateActionStatus.READY]: 0,
        [StateActionStatus.IN_PROGRESS]: 0,
        [StateActionStatus.COMPLETE]: 0,
      };

      const result = getStatusByPriority(counts);
      expect(result).toBe(StateActionStatus.NA);
    });
  });

  describe('edge cases', () => {
    it('should handle undefined props gracefully', () => {
      const { container } = render(<StatusTag label="" />);
      expect(container.firstChild).toBeNull();
    });

    it('should handle negative counts', () => {
      render(<StatusTag label="Test" action={StateActionStatus.COMPLETE} count={-1} />);
      expect(screen.getByText(/Test/)).toBeInTheDocument();
    });

    it('should handle very large counts', () => {
      render(<StatusTag label="Test" action={StateActionStatus.COMPLETE} count={99999} total={100000} />);
      expect(screen.getByText(/Test/)).toBeInTheDocument();
      expect(screen.getByText(/99999/)).toBeInTheDocument();
      expect(screen.getByText(/100000/)).toBeInTheDocument();
    });
  });
});
