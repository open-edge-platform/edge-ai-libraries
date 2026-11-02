// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom';

import { ScoreDisplay } from '../components/Search/ScoreDisplay';
import { ScoreBreakdown } from '../redux/search/search';

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, defaultValue?: string) => defaultValue || key,
      i18n: { changeLanguage: () => new Promise(() => {}) },
    }),
  };
});

const breakdown: ScoreBreakdown = {
  score: 1.0,
  raw_score: 0.533605,
  raw_score_min: 0.155595,
  raw_score_max: 0.533605,
  max_frame_score: 0.3893,
  top_n_avg_score: 0.3774,
  top_n_frame_count: 6,
  quality_score: 0.385139,
  contextual_weight: 0.770974,
};

describe('ScoreDisplay', () => {
  it('shows the normalized score and the raw score at the same time', () => {
    render(<ScoreDisplay relevanceScore={1.0} scoreBreakdown={breakdown} />);

    expect(screen.getByText('Relevance Score: 1.000')).toBeInTheDocument();
    expect(screen.getByText('raw 0.5336')).toBeInTheDocument();
    expect(screen.getByText('peak 0.3893')).toBeInTheDocument();
  });

  it('renders only the normalized score when no breakdown is available', () => {
    render(<ScoreDisplay relevanceScore={0.5} />);

    expect(screen.getByText('Relevance Score: 0.500')).toBeInTheDocument();
    expect(screen.queryByText(/^raw /)).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('falls back to N/A when the relevance score is missing', () => {
    render(<ScoreDisplay relevanceScore={undefined} />);

    expect(screen.getByText('Relevance Score: N/A')).toBeInTheDocument();
  });

  it('toggles the breakdown popover and lists every scoring stage', () => {
    render(<ScoreDisplay relevanceScore={1.0} scoreBreakdown={breakdown} />);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Score breakdown' }));

    const popover = screen.getByRole('dialog');
    expect(popover).toBeInTheDocument();
    expect(screen.getByText('Peak frame score')).toBeInTheDocument();
    expect(screen.getByText('0.3774 (n=6)')).toBeInTheDocument();
    expect(screen.getByText('Base quality')).toBeInTheDocument();
    expect(screen.getByText('0.771')).toBeInTheDocument();
    expect(screen.getByText('0.156 - 0.534')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Score breakdown' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('closes the popover on Escape', () => {
    render(<ScoreDisplay relevanceScore={1.0} scoreBreakdown={breakdown} />);

    fireEvent.click(screen.getByRole('button', { name: 'Score breakdown' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('flags a weak match when the peak frame similarity is low', () => {
    render(
      <ScoreDisplay relevanceScore={1.0} scoreBreakdown={{ ...breakdown, max_frame_score: 0.05 }} />,
    );

    expect(screen.getByText('weak match')).toBeInTheDocument();
  });

  it('does not flag a weak match for a strong peak frame similarity', () => {
    render(<ScoreDisplay relevanceScore={1.0} scoreBreakdown={breakdown} />);

    expect(screen.queryByText('weak match')).not.toBeInTheDocument();
  });
});
