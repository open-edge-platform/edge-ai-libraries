import { useState } from "react";
import { Cpu, Gauge, Gpu } from "lucide-react";
import { useMetrics } from "@/features/metrics/useMetrics.ts";
import {
  useMetricHistory,
  type MetricHistoryPoint,
  type GpuMetrics,
} from "@/hooks/useMetricHistory.ts";
import { MetricChart } from "@/features/metrics/MetricChart";
import { MetricCard } from "@/features/metrics/MetricCard";
import { GpuSectionContainer } from "@/features/pipeline-tests/components/test-progress/GpuSectionContainer";
import { useTestProgressData } from "@/features/pipeline-tests/hooks/useTestProgressData";
import { CHART_MAX_DATA_POINTS } from "@/features/pipeline-tests/utils/testProgressUtils";
import { cn } from "@/lib/utils";

interface TestProgressIndicatorProps {
  className?: string;
  forceDark?: boolean;
  useDemoStyles?: boolean;
  historyOverride?: MetricHistoryPoint[];
  metricsOverride?: {
    fps: number;
    cpu: number;
    memory: number;
    availableGpuIds: string[];
    gpuDetailedMetrics: Record<string, GpuMetrics>;
  };
}

export const TestProgressIndicator = ({
  className = "",
  forceDark = false,
  useDemoStyles = false,
  historyOverride,
  metricsOverride,
}: TestProgressIndicatorProps) => {
  const isSummary = !!metricsOverride;
  const liveMetrics = useMetrics();
  const liveHistory = useMetricHistory();
  const metrics = metricsOverride ?? {
    fps: liveMetrics.fps,
    cpu: liveMetrics.cpu,
    memory: liveMetrics.memory,
    availableGpuIds: liveMetrics.availableGpuIds,
    gpuDetailedMetrics: liveMetrics.gpuDetailedMetrics,
  };
  const history = historyOverride ?? liveHistory;
  const [selectedGpu, setSelectedGpu] = useState<number>(0);

  const summaryContainerClassName =
    "p-4 rounded-xl border-2 border-brand-accent/40 bg-gradient-to-br from-brand-accent/5 to-brand-accent-soft/5 shadow-lg shadow-brand-accent/10";
  const summaryCardClassName =
    "border-2 border-brand-accent/60 shadow-brand-accent/20 shadow-lg ring-2 ring-brand-accent/30";
  const summarySectionClassName =
    "border-2 border-brand-accent/40 shadow-brand-accent/20 ring-1 ring-brand-accent/20";
  const summaryIconClassName =
    "bg-gradient-to-br from-brand-accent/20 to-brand-accent-soft/20";
  const summaryTitleClassName = "text-summary-title";
  const summaryUnitClassName = "text-summary-unit";

  const {
    availableGpus,
    fpsData,
    cpuData,
    gpuChartData,
    gpuFrequencyData,
    gpuPowerData,
    displayedGpuUsage,
    cpuTempData,
    cpuFrequencyData,
    memoryData,
    fpsYAxisMax,
    cpuTempYAxisMax,
    cpuFrequencyYAxisMax,
    gpuPowerYAxisMax,
    gpuFrequencyYAxisMax,
    availableEngines,
    engineColors,
    engineLabels,
  } = useTestProgressData({ history, metrics, selectedGpu });

  const powerUsageSection = (
    <GpuSectionContainer
      title={
        <>
          Power Usage Over Time
          {availableGpus.length > 1 && (
            <>
              {" "}
              <span className="inline-block min-w-[0.5rem]">{selectedGpu}</span>
            </>
          )}
        </>
      }
      availableGpus={availableGpus}
      selectedGpu={selectedGpu}
      onGpuChange={setSelectedGpu}
      useDemoStyles={useDemoStyles}
      forceDark={forceDark}
      isSummary={isSummary}
      summarySectionClassName={summarySectionClassName}
      summaryTitleClassName={summaryTitleClassName}
    >
      <MetricChart
        title=""
        data={gpuPowerData}
        dataKeys={["gpuPower", "pkgPower"]}
        colors={["var(--color-red-chart)", "var(--color-yellow-chart)"]}
        unit=" W"
        yAxisDomain={[0, gpuPowerYAxisMax]}
        showLegend={true}
        className={cn(
          "!shadow-none !p-0",
          useDemoStyles && "!bg-transparent !border-0",
        )}
        labels={["GPU Power", "Package Power"]}
        maxDataPoints={CHART_MAX_DATA_POINTS}
        isSummary={isSummary}
        hideSummaryBorder={true}
        forceDark={forceDark}
        useDemoStyles={useDemoStyles}
      />
    </GpuSectionContainer>
  );

  const gpuUsageSection = (
    <GpuSectionContainer
      title={
        <>
          GPU
          {availableGpus.length > 1 && (
            <>
              {" "}
              <span className="inline-block min-w-[0.5rem]">{selectedGpu}</span>
            </>
          )}{" "}
          Usage Over Time
        </>
      }
      availableGpus={availableGpus}
      selectedGpu={selectedGpu}
      onGpuChange={setSelectedGpu}
      useDemoStyles={useDemoStyles}
      forceDark={forceDark}
      isSummary={isSummary}
      summarySectionClassName={summarySectionClassName}
      summaryTitleClassName={summaryTitleClassName}
    >
      <MetricChart
        title=""
        data={gpuChartData}
        dataKeys={availableEngines}
        colors={availableEngines.map((e) => engineColors[e])}
        unit="%"
        yAxisDomain={[0, 100]}
        labels={availableEngines.map((e) => engineLabels[e])}
        wrapLegend={true}
        className={cn(
          "!shadow-none !p-0",
          useDemoStyles && "!bg-transparent !border-0",
        )}
        maxDataPoints={CHART_MAX_DATA_POINTS}
        isSummary={isSummary}
        hideSummaryBorder={true}
        forceDark={forceDark}
        useDemoStyles={useDemoStyles}
      />
    </GpuSectionContainer>
  );

  return (
    <div
      className={cn(
        `space-y-4 ${className} text-foreground ${
          isSummary ? summaryContainerClassName : ""
        }`,
      )}
    >
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4">
        <div className="space-y-4">
          <MetricCard
            title={isSummary ? "Frame Rate Average" : "Frame Rate"}
            value={metrics.fps}
            unit="fps"
            icon={<Gauge className="h-6 w-6 text-magenta-chart" />}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
            summaryCardClassName={summaryCardClassName}
            summaryIconClassName={summaryIconClassName}
            summaryTitleClassName={summaryTitleClassName}
            summaryUnitClassName={summaryUnitClassName}
          />
          <MetricChart
            title="Frame Rate Over Time"
            data={fpsData}
            dataKeys={["value"]}
            colors={["var(--color-magenta-chart)"]}
            unit=" fps"
            yAxisDomain={[0, fpsYAxisMax]}
            showLegend={false}
            labels={["Frame Rate"]}
            maxDataPoints={CHART_MAX_DATA_POINTS}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
          />
          <MetricChart
            title="Memory Utilization Over Time"
            data={memoryData}
            dataKeys={["memory"]}
            colors={["var(--color-magenta-chart)"]}
            unit="%"
            yAxisDomain={[0, 100]}
            showLegend={false}
            labels={["Memory"]}
            maxDataPoints={CHART_MAX_DATA_POINTS}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
          />
        </div>

        <div className="space-y-4">
          <MetricCard
            title={isSummary ? "CPU Usage Average" : "CPU Usage"}
            value={metrics.cpu}
            unit="%"
            icon={<Cpu className="h-6 w-6 text-green-chart" />}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
            summaryCardClassName={summaryCardClassName}
            summaryIconClassName={summaryIconClassName}
            summaryTitleClassName={summaryTitleClassName}
            summaryUnitClassName={summaryUnitClassName}
          />
          <MetricChart
            title="CPU Usage Over Time"
            data={cpuData}
            dataKeys={["user"]}
            colors={["var(--color-green-chart)"]}
            unit="%"
            yAxisDomain={[0, 100]}
            showLegend={false}
            labels={["CPU Usage"]}
            maxDataPoints={CHART_MAX_DATA_POINTS}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
          />
          <MetricChart
            title="CPU Temperature Over Time"
            data={cpuTempData}
            dataKeys={["temp"]}
            colors={["var(--color-green-chart)"]}
            unit="°C"
            yAxisDomain={[0, cpuTempYAxisMax]}
            showLegend={false}
            labels={["Temperature"]}
            maxDataPoints={CHART_MAX_DATA_POINTS}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
          />
          <MetricChart
            title="CPU Frequency Over Time"
            data={cpuFrequencyData}
            dataKeys={["frequency"]}
            colors={["var(--color-green-chart)"]}
            unit=" GHz"
            yAxisDomain={[0, cpuFrequencyYAxisMax]}
            showLegend={false}
            labels={["Frequency"]}
            maxDataPoints={CHART_MAX_DATA_POINTS}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
          />
        </div>

        <div className="space-y-4">
          <MetricCard
            title={isSummary ? "GPU Usage Average" : "GPU Usage"}
            value={displayedGpuUsage}
            unit="%"
            icon={<Gpu className="h-6 w-6 text-yellow-chart" />}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
            summaryCardClassName={summaryCardClassName}
            summaryIconClassName={summaryIconClassName}
            summaryTitleClassName={summaryTitleClassName}
            summaryUnitClassName={summaryUnitClassName}
          />
          {!useDemoStyles && gpuUsageSection}
          {powerUsageSection}
          <GpuSectionContainer
            title={
              <>
                GPU
                {availableGpus.length > 1 && (
                  <>
                    {" "}
                    <span className="inline-block min-w-[0.5rem]">{selectedGpu}</span>
                  </>
                )}{" "}
                Frequency Over Time
              </>
            }
            availableGpus={availableGpus}
            selectedGpu={selectedGpu}
            onGpuChange={setSelectedGpu}
            useDemoStyles={useDemoStyles}
            forceDark={forceDark}
            isSummary={isSummary}
            summarySectionClassName={summarySectionClassName}
            summaryTitleClassName={summaryTitleClassName}
          >
            <MetricChart
              title=""
              data={gpuFrequencyData}
              dataKeys={["frequency"]}
              colors={["var(--color-yellow-chart)"]}
              unit=" GHz"
              yAxisDomain={[0, gpuFrequencyYAxisMax]}
              showLegend={false}
              labels={["Frequency"]}
              className={cn(
                "!shadow-none !p-0",
                useDemoStyles && "!bg-transparent !border-0",
              )}
              maxDataPoints={CHART_MAX_DATA_POINTS}
              isSummary={isSummary}
              hideSummaryBorder={true}
              forceDark={forceDark}
              useDemoStyles={useDemoStyles}
            />
          </GpuSectionContainer>
          {useDemoStyles && gpuUsageSection}
        </div>
      </div>
    </div>
  );
};
