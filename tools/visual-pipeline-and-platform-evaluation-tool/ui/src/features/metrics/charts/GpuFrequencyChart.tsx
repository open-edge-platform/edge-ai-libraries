/*SPDX-License-Identifier: Apache-2.0*/

import { GpuChartSection } from "@/features/metrics/charts/GpuChartSection";
import {
  type DashboardChartCommonProps,
  type DashboardSummarySectionProps,
} from "@/features/metrics/charts";

interface GpuFrequencyChartProps
  extends DashboardChartCommonProps,
    DashboardSummarySectionProps {
  data: Array<{ timestamp: number; frequency: number }>;
  yAxisMax: number;
  selectedGpu: number;
  availableGpus: number[];
  onGpuChange: (gpu: number) => void;
}

export const GpuFrequencyChart = ({
  data,
  yAxisMax,
  selectedGpu,
  availableGpus,
  onGpuChange,
  isSummary = false,
  forceDark = false,
  useDemoStyles = false,
  summarySectionClassName,
  summaryTitleClassName,
}: GpuFrequencyChartProps) => {
  return (
    <GpuChartSection
      title="GPU Frequency Over Time"
      chartData={data}
      chartDataKeys={["frequency"]}
      chartColors={["var(--color-yellow-chart)"]}
      chartUnit=" GHz"
      chartYAxisDomain={[0, yAxisMax]}
      chartLabels={["Frequency"]}
      selectedGpu={selectedGpu}
      availableGpus={availableGpus}
      onGpuChange={onGpuChange}
      isSummary={isSummary}
      forceDark={forceDark}
      useDemoStyles={useDemoStyles}
      summarySectionClassName={summarySectionClassName}
      summaryTitleClassName={summaryTitleClassName}
    />
  );
};
