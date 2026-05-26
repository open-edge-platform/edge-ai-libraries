import { useMemo, useState } from "react";
import { Clock, Cpu, Gauge, Gpu } from "lucide-react";
import { useTheme } from "next-themes";
import { MetricCard } from "@/features/metrics/MetricCard.tsx";
import {
  CHART_MAX_DATA_POINTS,
  CpuFrequencyChart,
  CpuTemperatureChart,
  CpuUsageChart,
  FrameRateChart,
  getRecentYAxisMax,
  GpuFrequencyChart,
  GpuPowerChart,
  GpuUsageChart,
  LatencyChart,
  MemoryUtilizationChart,
  NpuFrequencyChart,
  NpuPowerChart,
  NpuUsageChart,
} from "@/features/metrics/charts";
import { useMetrics } from "@/features/metrics/useMetrics.ts";
import {
  useMetricHistory,
  type GpuMetrics,
  type MetricHistoryPoint,
} from "@/hooks/useMetricHistory.ts";
import { useAppSelector } from "@/store/hooks.ts";
import { selectHasNPU } from "@/store/reducers/devices.ts";

interface MetricsDashboardProps {
  className?: string;
  forceDark?: boolean;
  useDemoStyles?: boolean;
  enableLatencyMetrics?: boolean;
  historyOverride?: MetricHistoryPoint[];
  metricsOverride?: {
    fps: number;
    cpu: number;
    memory: number;
    availableGpuIds: string[];
    gpuDetailedMetrics: Record<string, GpuMetrics>;
    latencyAvg?: number;
    latencyMin?: number;
    latencyMax?: number;
  };
}

export const MetricsDashboard = ({
  className = "",
  forceDark = false,
  useDemoStyles = false,
  enableLatencyMetrics = false,
  historyOverride,
  metricsOverride,
}: MetricsDashboardProps) => {
  const isSummary = !!metricsOverride;
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark" || forceDark;
  const liveMetrics = useMetrics();
  const liveHistory = useMetricHistory();
  const hasNpu = useAppSelector(selectHasNPU);
  const metrics = metricsOverride ?? {
    fps: liveMetrics.fps,
    cpu: liveMetrics.cpu,
    memory: liveMetrics.memory,
    availableGpuIds: liveMetrics.availableGpuIds,
    gpuDetailedMetrics: liveMetrics.gpuDetailedMetrics,
  };
  const history = historyOverride ?? liveHistory;
  const [selectedGpu, setSelectedGpu] = useState<number>(0);

  const summaryContainerClassName = isDarkTheme
    ? "p-4 border-2 border-energy-blue/40 bg-gradient-to-br from-energy-blue/5 to-energy-blue-tint-1/5 shadow-lg shadow-energy-blue/10"
    : "p-4 border-2 border-classic-blue/40 bg-gradient-to-br from-classic-blue/5 to-classic-blue/10 shadow-lg shadow-classic-blue/10";
  const summaryCardClassName = isDarkTheme
    ? "border-2 border-energy-blue/60 shadow-energy-blue/20 shadow-lg ring-2 ring-energy-blue/30"
    : "border-2 border-classic-blue/60 shadow-classic-blue/20 shadow-lg ring-2 ring-classic-blue/20";
  const summarySectionClassName = isDarkTheme
    ? "border-2 border-energy-blue/40 shadow-energy-blue/20 ring-1 ring-energy-blue/20"
    : "border-2 border-classic-blue/40 shadow-classic-blue/20 ring-1 ring-classic-blue/20";
  const summaryIconClassName = isDarkTheme
    ? "bg-gradient-to-br from-energy-blue/20 to-energy-blue-tint-1/20"
    : "bg-gradient-to-br from-classic-blue/15 to-classic-blue/25";
  const summaryTitleClassName = isDarkTheme
    ? "text-energy-blue-tint-1"
    : "text-classic-blue";
  const summaryUnitClassName = isDarkTheme
    ? "text-energy-blue-tint-2"
    : "text-classic-blue";

  const availableGpus = metrics.availableGpuIds.map((id) => parseInt(id));

  const fpsData = history.map((point) => ({
    timestamp: point.timestamp,
    value: point.fps ?? 0,
  }));

  const cpuData = history.map((point) => ({
    timestamp: point.timestamp,
    user: point.cpuUser ?? 0,
  }));

  const gpuData = useMemo(() => {
    const gpuId = selectedGpu.toString();
    return history.map((point) => {
      const gpu = point.gpus[gpuId];
      return {
        timestamp: point.timestamp,
        compute: gpu?.compute,
        render: gpu?.render,
        copy: gpu?.copy,
        video: gpu?.video,
        videoEnhance: gpu?.videoEnhance,
      };
    });
  }, [history, selectedGpu]);

  const availableEngines = useMemo(() => {
    const engines: string[] = [];
    const checkEngine = (key: string) => {
      return gpuData.some(
        (point) => point[key as keyof typeof point] !== undefined,
      );
    };

    if (checkEngine("compute")) engines.push("compute");
    if (checkEngine("render")) engines.push("render");
    if (checkEngine("copy")) engines.push("copy");
    if (checkEngine("video")) engines.push("video");
    if (checkEngine("videoEnhance")) engines.push("videoEnhance");

    return engines;
  }, [gpuData]);

  const gpuChartData = useMemo(() => {
    const normalizedGpuChartData: Array<
      { timestamp: number } & Record<string, number>
    > = gpuData.map((point) => {
      const chartPoint: { timestamp: number } & Record<string, number> = {
        timestamp: point.timestamp,
      };

      availableEngines.forEach((engine) => {
        chartPoint[engine] =
          (point[engine as keyof typeof point] as number) ?? 0;
      });

      return chartPoint;
    });

    return normalizedGpuChartData;
  }, [gpuData, availableEngines]);

  const gpuFrequencyData = useMemo(() => {
    const gpuId = selectedGpu.toString();
    const rawGpuFrequencyData = history.map((point) => ({
      timestamp: point.timestamp,
      frequency: point.gpus[gpuId]?.frequency ?? 0,
    }));

    return rawGpuFrequencyData;
  }, [history, selectedGpu]);

  const gpuPowerData = useMemo(() => {
    const gpuId = selectedGpu.toString();
    const rawGpuPowerData = history.map((point) => ({
      timestamp: point.timestamp,
      gpuPower: point.gpus[gpuId]?.gpuPower ?? 0,
      pkgPower: point.gpus[gpuId]?.pkgPower ?? 0,
    }));

    return rawGpuPowerData;
  }, [history, selectedGpu]);

  const displayedGpuUsage = useMemo(() => {
    const latestGpuPoint = gpuData.at(-1);
    if (!latestGpuPoint) {
      const gpuMetrics = metrics.gpuDetailedMetrics[selectedGpu.toString()];
      if (!gpuMetrics) return 0;

      return Math.max(
        gpuMetrics.compute ?? 0,
        gpuMetrics.render ?? 0,
        gpuMetrics.copy ?? 0,
        gpuMetrics.video ?? 0,
        gpuMetrics.videoEnhance ?? 0,
      );
    }

    return Math.max(
      latestGpuPoint.compute ?? 0,
      latestGpuPoint.render ?? 0,
      latestGpuPoint.copy ?? 0,
      latestGpuPoint.video ?? 0,
      latestGpuPoint.videoEnhance ?? 0,
    );
  }, [gpuData, metrics.gpuDetailedMetrics, selectedGpu]);

  const cpuTempData = history.map((point) => ({
    timestamp: point.timestamp,
    temp: point.cpuTemp ?? 0,
  }));

  const cpuFrequencyData = history.map((point) => ({
    timestamp: point.timestamp,
    frequency: point.cpuAvgFrequency ?? 0,
  }));

  const memoryData = history.map((point) => ({
    timestamp: point.timestamp,
    memory: point.memory ?? 0,
  }));

  const npuData = history.map((point) => ({
    timestamp: point.timestamp,
    usage: point.npuUsage ?? 0,
  }));

  const npuPowerData = history.map((point) => ({
    timestamp: point.timestamp,
    power: point.npuPower ?? 0,
  }));

  const npuFrequencyData = history.map((point) => ({
    timestamp: point.timestamp,
    frequency: point.npuFrequency ?? 0,
  }));

  const hasNpuData = hasNpu || npuData.some((point) => point.usage > 0);

  const latencyData = history.map((point) => ({
    timestamp: point.timestamp,
    avg: point.latencyAvg ?? 0,
    min: point.latencyMin ?? 0,
    max: point.latencyMax ?? 0,
  }));

  const hasLatencyData = latencyData.some(
    (point) => point.avg > 0 || point.min > 0 || point.max > 0,
  );

  const hasSummaryLatency =
    isSummary &&
    metricsOverride?.latencyAvg !== undefined &&
    metricsOverride?.latencyMin !== undefined &&
    metricsOverride?.latencyMax !== undefined;

  const showLatencySection =
    enableLatencyMetrics || hasLatencyData || hasSummaryLatency;

  const latencyYAxisMax = getRecentYAxisMax(
    latencyData.map((point) => Math.max(point.avg, point.min, point.max)),
    CHART_MAX_DATA_POINTS,
    1,
  );

  const fpsYAxisMax = getRecentYAxisMax(
    fpsData.map((point) => point.value),
    CHART_MAX_DATA_POINTS,
    1,
  );

  const cpuTempYAxisMax = getRecentYAxisMax(
    cpuTempData.map((point) => point.temp),
    CHART_MAX_DATA_POINTS,
    1,
  );

  const cpuFrequencyYAxisMax = getRecentYAxisMax(
    cpuFrequencyData.map((point) => point.frequency),
    CHART_MAX_DATA_POINTS,
    0.1,
  );

  const gpuPowerYAxisMax = getRecentYAxisMax(
    gpuPowerData.map((point) => Math.max(point.gpuPower, point.pkgPower)),
    CHART_MAX_DATA_POINTS,
    1,
  );

  const gpuFrequencyYAxisMax = getRecentYAxisMax(
    gpuFrequencyData.map((point) => point.frequency),
    CHART_MAX_DATA_POINTS,
    0.1,
  );

  const npuPowerYAxisMax = getRecentYAxisMax(
    npuPowerData.map((point) => point.power),
    CHART_MAX_DATA_POINTS,
    1,
  );

  const npuFrequencyYAxisMax = getRecentYAxisMax(
    npuFrequencyData.map((point) => point.frequency),
    CHART_MAX_DATA_POINTS,
    100,
  );

  const engineColors: Record<string, string> = {
    compute: "var(--color-yellow-chart)",
    render: "var(--color-orange-chart)",
    copy: "var(--color-purple-chart)",
    video: "var(--color-red-chart)",
    videoEnhance: "var(--color-geode-chart)",
  };

  const engineLabels: Record<string, string> = {
    compute: "Compute",
    render: "Render",
    copy: "Copy",
    video: "Video",
    videoEnhance: "Video Enhance",
  };

  return (
    <div
      className={`space-y-4 ${className} text-foreground ${
        isSummary ? summaryContainerClassName : ""
      }`}
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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
        {!isSummary && (
          <MetricCard
            title="CPU Usage"
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
        )}
        {!isSummary && (
          <MetricCard
            title="GPU Usage"
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
        )}
        {showLatencySection && (
          <MetricCard
            title={isSummary ? "Latency Average" : "Latency"}
            value={
              hasSummaryLatency
                ? metricsOverride!.latencyAvg!
                : (latencyData.at(-1)?.avg ?? 0)
            }
            unit="ms"
            icon={<Clock className="h-6 w-6 text-orange-chart" />}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
            summaryCardClassName={summaryCardClassName}
            summaryIconClassName={summaryIconClassName}
            summaryTitleClassName={summaryTitleClassName}
            summaryUnitClassName={summaryUnitClassName}
          />
        )}
        {hasNpuData && !isSummary && (
          <MetricCard
            title="NPU Usage"
            value={npuData.at(-1)?.usage ?? 0}
            unit="%"
            icon={<Gpu className="h-6 w-6 text-geode-chart" />}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
            summaryCardClassName={summaryCardClassName}
            summaryIconClassName={summaryIconClassName}
            summaryTitleClassName={summaryTitleClassName}
            summaryUnitClassName={summaryUnitClassName}
          />
        )}
      </div>

      <div
        className="grid grid-cols-1 gap-4 sm:grid-cols-2"
      >
        <FrameRateChart
          data={fpsData}
          yAxisMax={fpsYAxisMax}
          isSummary={isSummary}
          forceDark={forceDark}
          useDemoStyles={useDemoStyles}
        />
        <CpuUsageChart
          data={cpuData}
          isSummary={isSummary}
          forceDark={forceDark}
          useDemoStyles={useDemoStyles}
        />
        <MemoryUtilizationChart
          data={memoryData}
          isSummary={isSummary}
          forceDark={forceDark}
          useDemoStyles={useDemoStyles}
        />
        <CpuTemperatureChart
          data={cpuTempData}
          yAxisMax={cpuTempYAxisMax}
          isSummary={isSummary}
          forceDark={forceDark}
          useDemoStyles={useDemoStyles}
        />
        <CpuFrequencyChart
          data={cpuFrequencyData}
          yAxisMax={cpuFrequencyYAxisMax}
          isSummary={isSummary}
          forceDark={forceDark}
          useDemoStyles={useDemoStyles}
        />
        {!useDemoStyles && (
          <GpuUsageChart
            data={gpuChartData}
            dataKeys={availableEngines}
            colors={availableEngines.map((engine) => engineColors[engine])}
            labels={availableEngines.map((engine) => engineLabels[engine])}
            selectedGpu={selectedGpu}
            availableGpus={availableGpus}
            onGpuChange={setSelectedGpu}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
            summarySectionClassName={summarySectionClassName}
            summaryTitleClassName={summaryTitleClassName}
          />
        )}
        <GpuPowerChart
          data={gpuPowerData}
          yAxisMax={gpuPowerYAxisMax}
          selectedGpu={selectedGpu}
          availableGpus={availableGpus}
          onGpuChange={setSelectedGpu}
          isSummary={isSummary}
          forceDark={forceDark}
          useDemoStyles={useDemoStyles}
          summarySectionClassName={summarySectionClassName}
          summaryTitleClassName={summaryTitleClassName}
        />
        <GpuFrequencyChart
          data={gpuFrequencyData}
          yAxisMax={gpuFrequencyYAxisMax}
          selectedGpu={selectedGpu}
          availableGpus={availableGpus}
          onGpuChange={setSelectedGpu}
          isSummary={isSummary}
          forceDark={forceDark}
          useDemoStyles={useDemoStyles}
          summarySectionClassName={summarySectionClassName}
          summaryTitleClassName={summaryTitleClassName}
        />
        {useDemoStyles && (
          <GpuUsageChart
            data={gpuChartData}
            dataKeys={availableEngines}
            colors={availableEngines.map((engine) => engineColors[engine])}
            labels={availableEngines.map((engine) => engineLabels[engine])}
            selectedGpu={selectedGpu}
            availableGpus={availableGpus}
            onGpuChange={setSelectedGpu}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
            summarySectionClassName={summarySectionClassName}
            summaryTitleClassName={summaryTitleClassName}
          />
        )}
        {hasNpuData && (
          <NpuUsageChart
            data={npuData}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
          />
        )}
        {hasNpuData && (
          <NpuPowerChart
            data={npuPowerData}
            yAxisMax={npuPowerYAxisMax}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
          />
        )}
        {hasNpuData && (
          <NpuFrequencyChart
            data={npuFrequencyData}
            yAxisMax={npuFrequencyYAxisMax}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
          />
        )}
        {showLatencySection && (
          <LatencyChart
            data={latencyData}
            yAxisMax={latencyYAxisMax}
            isSummary={isSummary}
            forceDark={forceDark}
            useDemoStyles={useDemoStyles}
          />
        )}
      </div>
    </div>
  );
};
