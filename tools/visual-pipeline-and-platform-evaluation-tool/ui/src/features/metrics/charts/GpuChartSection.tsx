/*SPDX-License-Identifier: Apache-2.0*/

import { MetricChart } from "@/features/metrics/MetricChart";
import { GpuSelector } from "@/features/metrics/GpuSelector";
import {
  CHART_MAX_DATA_POINTS,
  type DashboardChartCommonProps,
  type DashboardSummarySectionProps,
} from "@/features/metrics/charts";

interface GpuChartSectionProps
  extends DashboardChartCommonProps,
    DashboardSummarySectionProps {
  title: string;
  chartData: Array<{ timestamp: number } & Record<string, number>>;
  chartDataKeys: string[];
  chartColors: string[];
  chartUnit: string;
  chartYAxisDomain: [number, number];
  chartLabels: string[];
  selectedGpu?: number;
  availableGpus?: number[];
  onGpuChange?: (gpu: number) => void;
  wrapLegend?: boolean;
}

export const GpuChartSection = ({
  title,
  chartData,
  chartDataKeys,
  chartColors,
  chartUnit,
  chartYAxisDomain,
  chartLabels,
  selectedGpu,
  availableGpus,
  onGpuChange,
  isSummary = false,
  forceDark = false,
  useDemoStyles = false,
  summarySectionClassName,
  summaryTitleClassName,
  wrapLegend = false,
}: GpuChartSectionProps) => {
  const hasGpuSelector =
    selectedGpu !== undefined && availableGpus && onGpuChange;

  return (
    <div
      className={`${
        useDemoStyles
          ? `${forceDark ? "bg-neutral-950/50" : "bg-card/80"}`
          : "bg-background"
      } ${useDemoStyles ? "rounded-xl shadow-2xl p-6" : "shadow-md p-4"} ${
        isSummary
          ? summarySectionClassName
          : useDemoStyles
            ? forceDark
              ? "border border-neutral-800/50"
              : "border border-border"
            : ""
      }`}
    >
      <h3
        className={`${
          useDemoStyles
            ? `text-[10px] font-semibold uppercase tracking-widest mb-6 ${
                isSummary ? summaryTitleClassName : "text-neutral-400"
              }`
            : "text-sm font-medium text-foreground mb-5"
        }`}
      >
        {title}
        {hasGpuSelector && availableGpus.length > 1 && (
          <>
            {" "}
            <span className="inline-block min-w-[0.5rem]">{selectedGpu}</span>
          </>
        )}
      </h3>
      <div className="flex gap-4 items-stretch overflow-hidden">
        {hasGpuSelector && (
          <div className="flex">
            <GpuSelector
              availableGpus={availableGpus}
              selectedGpu={selectedGpu}
              onGpuChange={onGpuChange}
            />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <MetricChart
            title=""
            data={chartData}
            dataKeys={chartDataKeys}
            colors={chartColors}
            unit={chartUnit}
            yAxisDomain={chartYAxisDomain}
            showLegend={true}
            className={`${useDemoStyles ? "!bg-transparent !border-0" : ""} !shadow-none !p-0`}
            labels={chartLabels}
            wrapLegend={wrapLegend}
            maxDataPoints={CHART_MAX_DATA_POINTS}
            isSummary={isSummary}
            hideSummaryBorder={true}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
          />
        </div>
      </div>
    </div>
  );
};
