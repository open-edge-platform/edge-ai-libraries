// Copyright (C) 2025 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { Dropdown, NumberInput, Tooltip } from '@carbon/react';
import { Information } from '@carbon/icons-react';
import { FC, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { TimeFilterSelection } from '../../redux/search/search';

export interface TimeFilterControlProps {
  timeFilter: TimeFilterSelection | null | undefined;
  onChange: (timeFilter: TimeFilterSelection | null) => void;
  idPrefix?: string;
  size?: 'sm' | 'md';
  disabled?: boolean;
  /**
   * Carbon's Tooltip has no autoAlign, so the caller picks a side that fits its
   * container. Callers rendering this near the bottom of a scrolling box should
   * open the tooltip upwards to avoid it being clipped.
   */
  tooltipAlign?: 'top' | 'top-start' | 'bottom' | 'bottom-start';
}

export const TimeFilterControl: FC<TimeFilterControlProps> = ({
  timeFilter,
  onChange,
  idPrefix = 'time-filter',
  size = 'sm',
  disabled = false,
  tooltipAlign = 'bottom-start',
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

  const handleUnitChange = (item: { id: string | number }) => {
    if (disabled) return;
    // If value is zero, changing unit should not trigger rerun upstream; keep filter unchanged.
    const currentVal = timeFilter?.value ?? 0;
    if (currentVal === 0) {
      return;
    }
    if (!timeFilter) {
      onChange({ value: 0, unit: item.id as any });
      return;
    }
    onChange({ ...timeFilter, unit: item.id as any });
  };

  const handleCustomValueChange = (raw: string | number | null | undefined) => {
    if (disabled) return;
    if (raw === '' || raw === null || raw === undefined) {
      onChange(null);
      return;
    }
    // Enforce digits-only positive integers
    const asString = String(raw).trim();
    if (!/^[0-9]+$/.test(asString)) return;
    const num = Number(asString);
    if (Number.isNaN(num)) return;
    if (num < 0) return;
    onChange({ value: num, unit: (timeFilter && timeFilter.unit) || 'minutes', source: 'input' });
  };

  return (
    <fieldset
      style={{
        border: 'none',
        margin: 0,
        padding: 0,
        minInlineSize: 0,
        maxWidth: '20rem',
      }}
    >
      <legend
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.25rem',
          padding: 0,
          marginBottom: '0.375rem',
          fontSize: '0.875rem',
          fontWeight: 600,
          lineHeight: 1.29,
          color: 'var(--cds-text-primary, #161616)',
        }}
      >
        {t('timeFilterGroupLabel', 'Date added')}
        <Tooltip
          align={tooltipAlign}
          label={t(
            'timeRangeHelp',
            'Search only videos added within a recent time window. Use 0 to search all videos.',
          )}
        >
          <button
            type='button'
            aria-label={t('timeFilterHelpLabel', 'About the date added filter')}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              padding: 0,
              border: 'none',
              background: 'none',
              cursor: 'pointer',
              color: 'inherit',
            }}
          >
            <Information size={16} />
          </button>
        </Tooltip>
      </legend>

      <div
        style={{
          display: 'flex',
          gap: '0.5rem',
          flexWrap: 'nowrap',
          alignItems: 'center',
        }}
      >
        <NumberInput
          id={`${idPrefix}-value`}
          label={t('timeFilterValueLabel', 'Time value')}
          hideLabel
          min={0}
          step={1}
          allowEmpty
          value={currentValue}
          size={size}
          onChange={(_, data) => handleCustomValueChange(data.value)}
          disabled={disabled}
        />
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
          disabled={disabled || currentValue <= 0}
        />
      </div>

      <p
        style={{
          marginTop: '0.375rem',
          fontSize: '0.75rem',
          lineHeight: 1.34,
          fontWeight: 400,
          color: 'var(--cds-text-helper, #6f6f6f)',
        }}
      >
        {summaryText}
      </p>
    </fieldset>
  );
};

export default TimeFilterControl;
