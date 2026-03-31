/*SPDX-License-Identifier: Apache-2.0*/

export const CHART_MAX_DATA_POINTS = 30;

export const getRecentYAxisMax = (
  values: number[],
  maxDataPoints: number,
  minMax: number,
) =>
  Math.max(minMax, 0, ...values.slice(-maxDataPoints).filter(Number.isFinite));

export interface DashboardChartCommonProps {
  isSummary?: boolean;
  forceDark?: boolean;
  useDemoStyles?: boolean;
}

export interface DashboardSummarySectionProps {
  summarySectionClassName?: string;
  summaryTitleClassName?: string;
}
