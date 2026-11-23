// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { TextInput, Toggle } from '@carbon/react';
import { FC, useRef, useState } from 'react';
import styled from 'styled-components';
import { useTranslation } from 'react-i18next';
import {
  ApplyIconButton,
  FilterBody,
  FilterFieldset,
  FilterHelp,
  FilterLegend,
  FilterLegendEnd,
  InfoTooltip,
  InfoTooltipAlign,
} from './FilterField';
import ValueBubbleSlider from './ValueBubbleSlider';
import { WEAK_MATCH_PEAK_THRESHOLD } from './ScoreDisplay';

// 0 to 1 with at most 3 decimals: 0, 0.2, 0.125, 1, 1.000.
const VALID_SCORE = /^(0(\.\d{1,3})?|1(\.0{1,3})?)$/;
// Mid-typing states that are not an error yet but cannot be applied either.
const INCOMPLETE_SCORE = /^([01]\.)?$/;

const roundScore = (value: number) => Math.round(value * 1000) / 1000;
export const formatMinPeakScore = (value: number) => String(roundScore(value));

/** Value the filter starts at when switched on: the deployment default if set, else 0.2. */
export const minPeakScoreOnValue = (defaultValue?: number | null) =>
  defaultValue && defaultValue > 0 ? defaultValue : WEAK_MATCH_PEAK_THRESHOLD;

export interface MinPeakScoreControlProps {
  /** Current minimum peak score; 0 means the filter is off. */
  value: number;
  /**
   * Called with the score to search with (0 when the filter is switched off).
   * Fires only when a value is applied: on slider release, Enter, leaving the
   * text box or clicking the apply icon; never while dragging or typing.
   */
  onChange: (value: number) => void;
  /** Value the slider jumps to when the filter is switched on. */
  onValue?: number;
  idPrefix?: string;
  disabled?: boolean;
  tooltipAlign?: InfoTooltipAlign;
  /** Fill the container instead of capping the width (e.g. in a filter card). */
  fullWidth?: boolean;
}

const InputWrap = styled.div`
  position: relative;
  width: 6rem;
  flex-shrink: 0;

  .cds--text-input {
    padding-inline-end: 2rem;
  }
  /* The red border and message flag an invalid value; the apply icon takes
     the spot Carbon's warning icon would use. */
  .cds--text-input__invalid-icon {
    display: none;
  }
`;

/**
 * Toggle + slider + text box for the minimum peak score search filter.
 *
 * Moving the slider or typing only changes a draft (the text box and slider
 * stay in sync); the draft is applied through `onChange` when the slider is
 * released or the typed value is confirmed with Enter, by leaving the box or
 * with the apply icon. The icon shows whether the draft has been applied. An
 * invalid typed value is flagged and reverts to the applied value when the
 * box is left. The value is read on mount only, so callers that switch
 * between queries should remount it with a `key`.
 */
export const MinPeakScoreControl: FC<MinPeakScoreControlProps> = ({
  value,
  onChange,
  onValue = WEAK_MATCH_PEAK_THRESHOLD,
  idPrefix = 'min-peak-score',
  disabled = false,
  tooltipAlign = 'bottom-start',
  fullWidth = false,
}) => {
  const { t } = useTranslation();
  const initial = value > 0 ? roundScore(value) : roundScore(onValue);
  const [enabled, setEnabled] = useState<boolean>(value > 0);
  // Draft shown by the slider and text box, and the last value sent out.
  const [score, setScore] = useState<number>(initial);
  const [applied, setApplied] = useState<number>(initial);
  const [text, setText] = useState<string>(formatMinPeakScore(initial));
  const [invalid, setInvalid] = useState<boolean>(false);
  // Read by release handlers, which can run before a re-render.
  const appliedRef = useRef(applied);

  const apply = (next: number) => {
    const rounded = roundScore(next);
    setScore(rounded);
    setText(formatMinPeakScore(rounded));
    setInvalid(false);
    if (rounded === appliedRef.current) return;
    appliedRef.current = rounded;
    setApplied(rounded);
    onChange(rounded);
  };

  const handleToggle = (checked: boolean) => {
    if (disabled) return;
    setEnabled(checked);
    setInvalid(false);
    if (checked) {
      const start = roundScore(onValue);
      appliedRef.current = start;
      setApplied(start);
      setScore(start);
      setText(formatMinPeakScore(start));
      onChange(start);
    } else {
      // Drop any unapplied draft so switching back on starts clean.
      setScore(applied);
      setText(formatMinPeakScore(applied));
      onChange(0);
    }
  };

  const handleSlider = (next: number) => {
    if (!enabled || disabled) return;
    const rounded = roundScore(next);
    setInvalid(false);
    setScore(rounded);
    setText(formatMinPeakScore(rounded));
  };

  const handleSliderRelease = (next: number) => {
    if (!enabled || disabled) return;
    apply(next);
  };

  const handleText = (raw: string) => {
    const trimmed = raw.trim();
    setText(raw);
    if (VALID_SCORE.test(trimmed)) {
      setInvalid(false);
      setScore(roundScore(Number(trimmed)));
    } else {
      setInvalid(!INCOMPLETE_SCORE.test(trimmed));
    }
  };

  /** Enter, blur or the apply icon: send a valid typed value, else revert. */
  const commitText = () => {
    if (!enabled || disabled) return;
    const trimmed = text.trim();
    if (VALID_SCORE.test(trimmed)) {
      apply(Number(trimmed));
    } else {
      setScore(appliedRef.current);
      setText(formatMinPeakScore(appliedRef.current));
      setInvalid(false);
    }
  };

  const controlsDisabled = disabled || !enabled;
  const trimmedText = text.trim();
  const textValid = VALID_SCORE.test(trimmedText);
  const pending = !controlsDisabled && textValid && roundScore(Number(trimmedText)) !== applied;

  return (
    <FilterFieldset $maxWidth={fullWidth ? undefined : '22rem'}>
      <FilterLegend>
        {t('minPeakScoreGroupLabel', 'Minimum peak score')}
        <InfoTooltip
          align={tooltipAlign}
          label={t('minPeakScoreHelp')}
          ariaLabel={t('minPeakScoreHelpLabel', 'About the minimum peak score filter')}
        />
        <FilterLegendEnd>
          <Toggle
            id={`${idPrefix}-toggle`}
            size='sm'
            labelText={t('minPeakScoreToggle', 'Filter by minimum peak score')}
            hideLabel
            labelA=''
            labelB=''
            aria-label={t('minPeakScoreToggle', 'Filter by minimum peak score')}
            toggled={enabled}
            disabled={disabled}
            onToggle={handleToggle}
          />
        </FilterLegendEnd>
      </FilterLegend>

      <FilterBody>
        <div style={{ flex: 1, minWidth: 0 }}>
          <ValueBubbleSlider
            id={`${idPrefix}-slider`}
            labelText={t('minPeakScoreSliderLabel', 'Minimum peak score slider')}
            min={0}
            max={1}
            step={0.001}
            value={score}
            format={formatMinPeakScore}
            disabled={controlsDisabled}
            onChange={handleSlider}
            onRelease={handleSliderRelease}
          />
        </div>
        <InputWrap>
          <TextInput
            id={`${idPrefix}-input`}
            labelText={t('minPeakScoreInputLabel', 'Minimum peak score value')}
            hideLabel
            size='sm'
            inputMode='decimal'
            value={text}
            disabled={controlsDisabled}
            invalid={invalid}
            invalidText={t('minPeakScoreInvalid', 'Enter a number from 0 to 1 with up to 3 decimals.')}
            onChange={(ev) => handleText(ev.currentTarget.value)}
            onBlur={commitText}
            onKeyDown={(ev) => {
              if (ev.key === 'Enter') {
                ev.preventDefault();
                commitText();
              }
            }}
          />
          <ApplyIconButton
            pending={pending}
            disabled={controlsDisabled}
            pendingLabel={t('minPeakScoreApply', 'Apply minimum peak score (Enter)')}
            appliedLabel={t('minPeakScoreApplied', 'Minimum peak score applied')}
            testId={`${idPrefix}-apply`}
            onApply={commitText}
          />
        </InputWrap>
      </FilterBody>

      <FilterHelp>
        {enabled
          ? t('minPeakScoreSummary', { value: formatMinPeakScore(applied) })
          : t('minPeakScoreSummaryOff', 'No score limit. All matches are returned.')}
      </FilterHelp>
    </FilterFieldset>
  );
};

export default MinPeakScoreControl;
