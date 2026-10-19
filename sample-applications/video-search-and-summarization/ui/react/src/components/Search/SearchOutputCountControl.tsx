// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
import { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { FilterBody, FilterFieldset, FilterHelp, FilterLegend, InfoTooltip, InfoTooltipAlign } from './FilterField';
import ValueBubbleSlider from './ValueBubbleSlider';

/** Upper bound of the slider; matches the backend's default AGGREGATION_MAX_RESULTS. */
export const SEARCH_OUTPUT_COUNT_MAX = 20;

export interface SearchOutputCountControlProps {
  value: number;
  onChange: (value: number) => void;
  idPrefix?: string;
  tooltipAlign?: InfoTooltipAlign;
}

/** Slider choosing how many of a query's ranked results are shown. */
export const SearchOutputCountControl: FC<SearchOutputCountControlProps> = ({
  value,
  onChange,
  idPrefix = 'search-output-count',
  tooltipAlign = 'bottom-start',
}) => {
  const { t } = useTranslation();

  return (
    <FilterFieldset>
      <FilterLegend>
        {t('searchOutputCount', 'Search output count')}
        <InfoTooltip
          align={tooltipAlign}
          label={t('searchOutputCountHelp')}
          ariaLabel={t('searchOutputCountHelpLabel', 'About the search output count')}
        />
      </FilterLegend>

      <FilterBody>
        <div style={{ flex: 1, minWidth: 0 }}>
          <ValueBubbleSlider
            id={`${idPrefix}-slider`}
            labelText={t('searchOutputCountSliderLabel', 'Search output count slider')}
            min={1}
            max={SEARCH_OUTPUT_COUNT_MAX}
            step={1}
            value={value}
            onChange={onChange}
          />
        </div>
      </FilterBody>

      <FilterHelp>{t('searchOutputCountSummary', { count: value })}</FilterHelp>
    </FilterFieldset>
  );
};

export default SearchOutputCountControl;
