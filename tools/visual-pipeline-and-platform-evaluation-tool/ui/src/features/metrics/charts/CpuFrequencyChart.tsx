/*SPDX-License-Identifier: Apache-2.0*/

import { MetricChart } from "@/features/metrics/MetricChart";
import {
  CHART_MAX_DATA_POINTS,
  type DashboardChartCommonProps,
} from "@/features/metrics/charts";

interface CpuFrequencyChartProps extends DashboardChartCommonProps {
  data: Array<{ timestamp: number; frequency: number }>;
  yAxisMax: number;
}

export const CpuFrequencyChart = ({
  data,
  yAxisMax,
  isSummary = false,
  forceDark = false,
  useDemoStyles = false,
}: CpuFrequencyChartProps) => {
  return (
    <MetricChart
      title="CPU Frequency Over Time"
      data={data}
      dataKeys={["frequency"]}
      colors={["var(--color-green-chart)"]}
      unit=" GHz"
      yAxisDomain={[0, yAxisMax]}
      showLegend={false}
      labels={["Frequency"]}
      maxDataPoints={CHART_MAX_DATA_POINTS}
      isSummary={isSummary}
      forceDark={forceDark}
      useDemoStyles={useDemoStyles}
    />
  );
};
