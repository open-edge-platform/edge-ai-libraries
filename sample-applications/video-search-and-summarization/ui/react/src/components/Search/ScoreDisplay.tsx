// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';

import { ScoreBreakdown } from '../../redux/search/search';

/**
 * Peak frame similarity below which a segment is flagged as a weak match.
 * Normalized and raw scores are both query-relative, so the peak frame
 * similarity is the only near-absolute signal available to the user.
 */
export const WEAK_MATCH_PEAK_THRESHOLD = 0.2;

const Wrapper = styled.div`
  display: flex;
  flex-flow: column nowrap;
  gap: 0.125rem;
  position: relative;
`;

const PrimaryScore = styled.div`
  color: var(--color-text-primary);
  font-size: 0.875rem;
  font-weight: 600;
`;

const SecondaryRow = styled.div`
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.375rem;
  color: var(--color-gray-7, #6b7280);
  font-size: 0.75rem;
  font-weight: 400;
`;

const RangeBar = styled.div`
  position: relative;
  width: 100%;
  max-width: 12rem;
  height: 0.25rem;
  margin-top: 0.125rem;
  border-radius: 0.125rem;
  background-color: var(--color-gray-3, #e5e7eb);
`;

const RangeMarker = styled.div<{ $position: number }>`
  position: absolute;
  top: -0.125rem;
  left: ${({ $position }) => `${$position * 100}%`};
  width: 0.25rem;
  height: 0.5rem;
  border-radius: 0.125rem;
  background-color: var(--color-info, #2563eb);
  transform: translateX(-50%);
`;

const WeakMatchChip = styled.span`
  padding: 0 0.375rem;
  border-radius: 4px;
  background-color: var(--color-warning, #b45309);
  color: white;
  font-size: 0.6875rem;
  font-weight: 500;
`;

const InfoButton = styled.button`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1rem;
  height: 1rem;
  padding: 0;
  border: 1px solid currentColor;
  border-radius: 50%;
  background: transparent;
  color: inherit;
  font-size: 0.625rem;
  line-height: 1;
  cursor: pointer;

  &:hover,
  &:focus-visible {
    color: var(--color-info, #2563eb);
  }
`;

const Popover = styled.div`
  position: absolute;
  bottom: calc(100% + 0.5rem);
  left: 0;
  z-index: 20;
  min-width: 16rem;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--color-gray-3, #e5e7eb);
  border-radius: 0.375rem;
  background-color: var(--color-background, #ffffff);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  color: var(--color-text-primary);
  font-size: 0.75rem;
  font-weight: 400;
`;

const PopoverTitle = styled.div`
  margin-bottom: 0.375rem;
  font-weight: 600;
`;

const PopoverRow = styled.div`
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.0625rem 0;
`;

const PopoverLabel = styled.span`
  color: var(--color-gray-7, #6b7280);
`;

const PopoverValue = styled.span`
  font-variant-numeric: tabular-nums;
`;

const PopoverNote = styled.p`
  margin: 0.375rem 0 0;
  color: var(--color-gray-7, #6b7280);
  font-size: 0.6875rem;
  line-height: 1.3;
`;

const format = (value: number | null | undefined, digits = 4): string =>
  typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';

export interface ScoreDisplayProps {
  relevanceScore?: number | null;
  scoreBreakdown?: ScoreBreakdown | null;
}

/**
 * Renders the query-normalized relevance score together with the raw,
 * pre-normalization segment score, plus an on-demand breakdown of every
 * stage the search service used to produce them.
 */
export const ScoreDisplay: FC<ScoreDisplayProps> = ({ relevanceScore, scoreBreakdown }) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return undefined;

    const onPointerDown = (event: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) close();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };

    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open, close]);

  const rawScore = scoreBreakdown?.raw_score;
  const rawMin = scoreBreakdown?.raw_score_min;
  const rawMax = scoreBreakdown?.raw_score_max;
  const peakScore = scoreBreakdown?.max_frame_score;
  const hasRaw = typeof rawScore === 'number' && Number.isFinite(rawScore);
  const hasPeak = typeof peakScore === 'number' && Number.isFinite(peakScore);

  const hasRange =
    hasRaw &&
    typeof rawMin === 'number' &&
    typeof rawMax === 'number' &&
    Number.isFinite(rawMin) &&
    Number.isFinite(rawMax) &&
    rawMax > rawMin;
  const rangePosition = hasRange ? Math.min(1, Math.max(0, (rawScore! - rawMin!) / (rawMax! - rawMin!))) : 0;
  const rangeLabel = `${t('RawScoreRangeLabel', 'Raw range (this query)')}: ${format(rawMin, 3)} - ${format(rawMax, 3)}`;

  return (
    <Wrapper ref={wrapperRef} className='score-display'>
      <PrimaryScore>
        {`${t('RelevanceScore', 'Relevance Score')}: ${
          typeof relevanceScore === 'number' ? relevanceScore.toFixed(3) : t('naTag', 'N/A')
        }`}
      </PrimaryScore>

      {(hasRaw || hasPeak) && (
        <SecondaryRow>
          {hasRaw && <span>{`${t('RawScoreShort', 'raw')} ${format(rawScore)}`}</span>}
          {hasRaw && hasPeak && <span aria-hidden='true'>·</span>}
          {hasPeak && <span>{`${t('PeakFrameScoreShort', 'peak')} ${format(peakScore)}`}</span>}
          {hasPeak && peakScore! < WEAK_MATCH_PEAK_THRESHOLD && (
            <WeakMatchChip>{t('WeakMatch', 'weak match')}</WeakMatchChip>
          )}
          {scoreBreakdown && (
            <InfoButton
              type='button'
              aria-expanded={open}
              aria-label={t('ScoreBreakdownTitle', 'Score breakdown')}
              onClick={() => setOpen((current) => !current)}
            >
              i
            </InfoButton>
          )}
        </SecondaryRow>
      )}

      {hasRange && (
        <RangeBar role='img' aria-label={rangeLabel} title={rangeLabel}>
          <RangeMarker $position={rangePosition} />
        </RangeBar>
      )}

      {open && scoreBreakdown && (
        <Popover role='dialog' aria-label={t('ScoreBreakdownTitle', 'Score breakdown')}>
          <PopoverTitle>{t('ScoreBreakdownTitle', 'Score breakdown')}</PopoverTitle>
          <PopoverRow>
            <PopoverLabel>{t('PeakFrameScore', 'Peak frame score')}</PopoverLabel>
            <PopoverValue>{format(scoreBreakdown.max_frame_score)}</PopoverValue>
          </PopoverRow>
          <PopoverRow>
            <PopoverLabel>{t('TopNAverage', 'Top-N frame average')}</PopoverLabel>
            <PopoverValue>
              {`${format(scoreBreakdown.top_n_avg_score)}${
                scoreBreakdown.top_n_frame_count ? ` (n=${scoreBreakdown.top_n_frame_count})` : ''
              }`}
            </PopoverValue>
          </PopoverRow>
          <PopoverRow>
            <PopoverLabel>{t('BaseQuality', 'Base quality')}</PopoverLabel>
            <PopoverValue>{format(scoreBreakdown.quality_score)}</PopoverValue>
          </PopoverRow>
          <PopoverRow>
            <PopoverLabel>{t('ContextWeight', 'Context weight')}</PopoverLabel>
            <PopoverValue>{format(scoreBreakdown.contextual_weight, 3)}</PopoverValue>
          </PopoverRow>
          <PopoverRow>
            <PopoverLabel>{t('RawScore', 'Raw score')}</PopoverLabel>
            <PopoverValue>{format(scoreBreakdown.raw_score)}</PopoverValue>
          </PopoverRow>
          <PopoverRow>
            <PopoverLabel>{t('NormalizedScore', 'Normalized score')}</PopoverLabel>
            <PopoverValue>{format(relevanceScore ?? scoreBreakdown.score)}</PopoverValue>
          </PopoverRow>
          {hasRange && (
            <PopoverRow>
              <PopoverLabel>{t('RawScoreRangeLabel', 'Raw range (this query)')}</PopoverLabel>
              <PopoverValue>{`${format(rawMin, 3)} - ${format(rawMax, 3)}`}</PopoverValue>
            </PopoverRow>
          )}
          <PopoverNote>
            {t(
              'ScoreBreakdownNote',
              'Raw and normalized scores are relative to this query only. Peak frame score is the underlying similarity and is the best indicator of whether the clip truly matches.',
            )}
          </PopoverNote>
        </Popover>
      )}
    </Wrapper>
  );
};

export default ScoreDisplay;
