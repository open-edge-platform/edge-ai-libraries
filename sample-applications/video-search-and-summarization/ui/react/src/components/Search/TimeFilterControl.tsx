// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Dropdown, NumberInput } from '@carbon/react';
import { FC, FocusEvent, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import styled from 'styled-components';
import { TimeFilterSelection } from '../../redux/search/search';
import {
  ApplyIconButton,
  FilterBody,
  FilterFieldset,
  FilterHelp,
  FilterLegend,
  InfoTooltip,
  InfoTooltipAlign,
} from './FilterField';

// Width of Carbon's +/- stepper group, per input size.
const STEPPERS_WIDTH = { sm: '4rem', md: '5rem' } as const;

const NumberWrap = styled.div<{ $steppers: string }>`
  position: relative;
  flex: 1 1 auto;
  min-width: 0;

  /* Room for the apply icon, which sits just left of the steppers in the
     slot Carbon's invalid icon would use (the red border and message already
     flag an invalid value). */
  .cds--number.cds--number input[type='number'] {
    padding-inline-end: calc(${({ $steppers }) => $steppers} + 2rem);
  }
  .cds--number__invalid {
    display: none;
  }
`;

type Draft = number | '';

const isValidDraft = (draft: Draft) => draft === '' || (Number.isInteger(draft) && draft >= 0);

export interface TimeFilterControlProps {
  timeFilter: TimeFilterSelection | null | undefined;
  /**
   * Called when a value is applied: Enter, leaving the number field, the
   * apply icon, or picking a unit. Never while a number is being typed or
   * stepped.
   */
  onChange: (timeFilter: TimeFilterSelection | null) => void;
  idPrefix?: string;
  size?: 'sm' | 'md';
  disabled?: boolean;
  /**
   * Carbon's Tooltip has no autoAlign, so the caller picks a side that fits its
   * container. Callers rendering this near the bottom of a scrolling box should
   * open the tooltip upwards to avoid it being clipped.
   */
  tooltipAlign?: InfoTooltipAlign;
  /** Fill the container instead of capping the width (e.g. in a filter card). */
  fullWidth?: boolean;
}

/**
 * "Date added" filter: a whole number and a unit. Typing or using the +/-
 * steppers only edits a draft; it is applied with Enter, by leaving the
 * number field or with the apply icon, which also shows whether the draft has
 * been applied. Picking a unit applies straight away (with the draft number).
 */
export const TimeFilterControl: FC<TimeFilterControlProps> = ({
  timeFilter,
  onChange,
  idPrefix = 'time-filter',
  size = 'sm',
  disabled = false,
  tooltipAlign = 'bottom-start',
  fullWidth = false,
}) => {
  const { t } = useTranslation();

  const timeUnitItems = useMemo(
    () => [
      { id: 'minutes', label: t('timeFilterMinutes', 'Minutes') },
      { id: 'hours', label: t('timeFilterHours', 'Hours') },
      { id: 'days', label: t('timeFilterDays', 'Days') },
      { id: 'weeks', label: t('timeFilterWeeks', 'Weeks') },
    ],
    [t],
  );

  const selectedUnitItem = useMemo(() => {
    if (!timeFilter || !timeFilter.unit) return timeUnitItems[0];
    const match = timeUnitItems.find((item) => item.id === timeFilter.unit);
    return match || timeUnitItems[0];
  }, [timeFilter, timeUnitItems]);

  const currentValue = timeFilter?.value ?? 0;
  const [draft, setDraft] = useState<Draft>(currentValue);
  const [invalid, setInvalid] = useState(false);

  // Follow the applied value when it changes from outside (or after applying).
  useEffect(() => {
    setDraft(currentValue);
    setInvalid(false);
  }, [currentValue]);

  const draftValid = isValidDraft(draft);
  const draftNumber = draft === '' ? 0 : draft;
  const pending = !disabled && draftValid && draftNumber !== currentValue;

  // The backend turns this into `created_at BETWEEN (now - value) AND now`,
  // where `created_at` is when DataPrep ingested the video. Spell that out so
  // the control is not mistaken for a video-duration filter.
  const summaryText = useMemo(() => {
    if (!currentValue || currentValue <= 0) {
      return t('timeFilterSummaryAll', 'No time limit. Every video is searched.');
    }

    const unitLabel = String(selectedUnitItem.label).toLowerCase();

    return t('timeFilterSummary', {
      defaultValue: 'Only videos added in the last {{value}} {{unit}} are searched.',
      value: currentValue,
      unit: currentValue === 1 ? unitLabel.replace(/s$/, '') : unitLabel,
    });
  }, [currentValue, selectedUnitItem, t]);

  const unitOf = (selection: TimeFilterSelection | null | undefined) => (selection && selection.unit) || 'minutes';

  /** Enter, leaving the field or the apply icon: send a valid draft, else revert. */
  const commit = () => {
    if (disabled) return;
    setInvalid(false);
    if (!draftValid) {
      setDraft(currentValue);
      return;
    }
    setDraft(draftNumber);
    if (draftNumber === currentValue) return;
    onChange(draft === '' ? null : { value: draftNumber, unit: unitOf(timeFilter), source: 'input' });
  };

  const handleValueChange = (raw: number | string | undefined) => {
    if (disabled) return;
    const next: Draft = raw === '' || raw === undefined ? '' : Number(raw);
    setDraft(next);
    setInvalid(!isValidDraft(next));
  };

  const handleUnitChange = (item: { id: string | number }) => {
    if (disabled) return;
    // The unit means nothing without a number; the dropdown is disabled then.
    if (!draftValid || draftNumber === 0) return;
    onChange({ ...(timeFilter ?? {}), value: draftNumber, unit: item.id as TimeFilterSelection['unit'] });
  };

  const handleNumberBlur = (ev: FocusEvent<HTMLDivElement>) => {
    // Moving between the input and its own +/- buttons is still editing.
    if (ev.currentTarget.contains(ev.relatedTarget as Node | null)) return;
    commit();
  };

  return (
    <FilterFieldset $maxWidth={fullWidth ? undefined : '20rem'}>
      <FilterLegend>
        {t('timeFilterGroupLabel', 'Date added')}
        <InfoTooltip
          align={tooltipAlign}
          label={t(
            'timeRangeHelp',
            'Search only videos added within a recent time window. Use 0 to search all videos.',
          )}
          ariaLabel={t('timeFilterHelpLabel', 'About the date added filter')}
        />
      </FilterLegend>

      <FilterBody>
        <NumberWrap $steppers={STEPPERS_WIDTH[size]} onBlur={handleNumberBlur}>
          <NumberInput
            id={`${idPrefix}-value`}
            label={t('timeFilterValueLabel', 'Time value')}
            hideLabel
            min={0}
            step={1}
            allowEmpty
            value={draft}
            size={size}
            invalid={invalid}
            invalidText={t('timeFilterInvalid', 'Enter a whole number, 0 or more.')}
            onChange={(_, data) => handleValueChange(data.value)}
            onKeyDown={(ev) => {
              if (ev.key === 'Enter') {
                ev.preventDefault();
                commit();
              }
            }}
            disabled={disabled}
          />
          <ApplyIconButton
            pending={pending}
            disabled={disabled}
            right={`calc(${STEPPERS_WIDTH[size]} + 0.25rem)`}
            pendingLabel={t('timeFilterApply', 'Apply date added filter (Enter)')}
            appliedLabel={t('timeFilterApplied', 'Date added filter applied')}
            testId={`${idPrefix}-apply`}
            onApply={commit}
          />
        </NumberWrap>
        <Dropdown
          id={`${idPrefix}-unit`}
          titleText={t('timeFilterUnit', 'Unit')}
          hideLabel
          label={t('timeFilterUnit', 'Unit')}
          items={timeUnitItems}
          itemToString={(item) => (item ? String(item.label) : '')}
          selectedItem={selectedUnitItem}
          onChange={({ selectedItem }) => {
            if (selectedItem) {
              handleUnitChange(selectedItem as { id: string | number });
            }
          }}
          size={size}
          // The unit is meaningless at 0 and handleUnitChange already ignores
          // it; disabling makes that visible instead of silently inert.
          disabled={disabled || !draftValid || draftNumber <= 0}
        />
      </FilterBody>

      <FilterHelp>{summaryText}</FilterHelp>
    </FilterFieldset>
  );
};

export default TimeFilterControl;
