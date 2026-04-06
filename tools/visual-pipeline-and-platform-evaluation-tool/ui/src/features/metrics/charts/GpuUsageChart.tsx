/*SPDX-License-Identifier: Apache-2.0*/

import { GpuChartSection } from "@/features/metrics/charts/GpuChartSection";
import {
  type DashboardChartCommonProps,
  type DashboardSummarySectionProps,
} from "@/features/metrics/charts";

interface GpuUsageChartProps
  extends DashboardChartCommonProps,
    DashboardSummarySectionProps {
  data: Array<{ timestamp: number } & Record<string, number>>;
  dataKeys: string[];
  colors: string[];
  labels: string[];
  selectedGpu: number;
  availableGpus: number[];
  onGpuChange: (gpu: number) => void;
}

export const GpuUsageChart = ({
  data,
  dataKeys,
  colors,
  labels,
  selectedGpu,
  availableGpus,
  onGpuChange,
  isSummary = false,
  forceDark = false,
  useDemoStyles = false,
  summarySectionClassName,
  summaryTitleClassName,
}: GpuUsageChartProps) => {
  return (
    <GpuChartSection
      title="GPU Usage Over Time"
      chartData={data}
      chartDataKeys={dataKeys}
      chartColors={colors}
      chartUnit="%"
      chartYAxisDomain={[0, 100]}
      chartLabels={labels}
      selectedGpu={selectedGpu}
      availableGpus={availableGpus}
      onGpuChange={onGpuChange}
      isSummary={isSummary}
      forceDark={forceDark}
      useDemoStyles={useDemoStyles}
      summarySectionClassName={summarySectionClassName}
      summaryTitleClassName={summaryTitleClassName}
      wrapLegend={true}
    />
  );
};
