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
}

export const TimeFilterControl: FC<TimeFilterControlProps> = ({
  timeFilter,
  onChange,
  idPrefix = 'time-filter',
  size = 'sm',
  disabled = false,
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
    <div
      style={{
        display: 'flex',
        gap: '0.75rem',
        flexWrap: 'nowrap',
        alignItems: 'center',
        justifyContent: 'center',
        maxWidth: '20rem',
      }}
    >
      <NumberInput
        id={`${idPrefix}-value`}
        label={t('timeRangeValue', 'Time Value')}
        min={0}
        step={1}
        allowEmpty
        value={currentValue}
        size={size}
        onChange={(_, data) => handleCustomValueChange(data.value)}
        disabled={disabled}
        // style={{ width: '9rem' }}
      />
      <Dropdown
        id={`${idPrefix}-unit`}
        label={t('Unit', 'Unit')}
        titleText={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
            {t('Unit', 'Unit')}
            <Tooltip
              align='bottom'
              label={t('timeRangeHelp', 'Select the time range used to filter video results.')}
            >
              <Information size={8} />
            </Tooltip>
          </span>
        }
        items={timeUnitItems}
        itemToString={(item) => (item ? String(item.label) : '')}
        selectedItem={selectedUnitItem}
        onChange={({ selectedItem }) => {
          if (selectedItem) {
            handleUnitChange(selectedItem as { id: string | number });
          }
        }}
        size={size}
        disabled={disabled}
      />
    </div>
  );
};

export default TimeFilterControl;
