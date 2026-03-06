import { useMemo, useState } from "react";
import { Cpu, Gauge, Gpu } from "lucide-react";
import { useMetrics } from "@/features/metrics/useMetrics.ts";
import {
  useMetricHistory,
  type MetricHistoryPoint,
  type GpuMetrics,
} from "@/hooks/useMetricHistory.ts";
import { MetricChart } from "@/features/metrics/MetricChart";
import { GpuSelector } from "@/features/metrics/GpuSelector";

const CHART_MAX_DATA_POINTS = 30;

const getRecentYAxisMax = (
  values: number[],
  maxDataPoints: number,
  minMax: number,
  headroomFactor = 1.15,
) => {
  const recentValues = values.slice(-maxDataPoints).filter(Number.isFinite);
  if (recentValues.length === 0) return minMax;

  const recentMax = Math.max(...recentValues, 0);
  if (recentMax <= 0) return minMax;

  return Math.max(recentMax * headroomFactor, minMax);
};

const stabilizeSingleZeroDropSeries = <T extends Record<string, number>>(
  data: T[],
  keys: (keyof T)[],
): T[] => {
  const previousByKey: Partial<Record<keyof T, number>> = {};
  const zeroStreakByKey: Partial<Record<keyof T, number>> = {};

  return data.map((point) => {
    const stabilizedPoint = { ...point };

    keys.forEach((key) => {
      const value = point[key];
      const previousValue = previousByKey[key] ?? 0;
      const currentZeroStreak = zeroStreakByKey[key] ?? 0;

      if (value === 0 && previousValue > 0) {
        const nextZeroStreak = currentZeroStreak + 1;
        zeroStreakByKey[key] = nextZeroStreak;
        if (nextZeroStreak === 1) {
          stabilizedPoint[key] = previousValue as T[keyof T];
          return;
        }
      } else {
        zeroStreakByKey[key] = 0;
      }

      if (value > 0) {
        previousByKey[key] = value;
      }
    });

    return stabilizedPoint;
  });
};

const stabilizeSingleZeroDropOptionalSeries = <
  T extends Record<string, number | undefined>,
>(
  data: T[],
  keys: (keyof T)[],
): T[] => {
  const previousByKey: Partial<Record<keyof T, number>> = {};
  const zeroStreakByKey: Partial<Record<keyof T, number>> = {};

  return data.map((point) => {
    const stabilizedPoint = { ...point };

    keys.forEach((key) => {
      const value = point[key];
      if (value === undefined) return;

      const previousValue = previousByKey[key] ?? 0;
      const currentZeroStreak = zeroStreakByKey[key] ?? 0;

      if (value === 0 && previousValue > 0) {
        const nextZeroStreak = currentZeroStreak + 1;
        zeroStreakByKey[key] = nextZeroStreak;
        if (nextZeroStreak === 1) {
          stabilizedPoint[key] = previousValue as T[keyof T];
          return;
        }
      } else {
        zeroStreakByKey[key] = 0;
      }

      if (value > 0) {
        previousByKey[key] = value;
      }
    });

    return stabilizedPoint;
  });
};

interface MetricCardProps {
  title: string;
  value: number;
  unit: string;
  icon: React.ReactNode;
  isSummary?: boolean;
  forceDark?: boolean;
  useDemoStyles?: boolean;
}

const MetricCard = ({
  title,
  value,
  unit,
  icon,
  isSummary = false,
  forceDark = false,
  useDemoStyles = false,
}: MetricCardProps) => (
  <div
    className={`${
      useDemoStyles
        ? `${forceDark ? "bg-neutral-950/50" : "bg-card/80"}`
        : "bg-background"
    } ${useDemoStyles ? "rounded-xl shadow-2xl p-6" : "shadow-md p-4"} flex items-center space-x-3 transition-all ${
      isSummary
        ? "border-2 border-energy-blue/60 shadow-energy-blue/20 shadow-lg ring-2 ring-energy-blue/30"
        : useDemoStyles
          ? forceDark
            ? "border border-neutral-800/50"
            : "border border-border"
          : ""
    }`}
  >
    <div
      className={`shrink-0 p-3 rounded-lg backdrop-blur-sm ${
        useDemoStyles
          ? isSummary
            ? "bg-gradient-to-br from-energy-blue/20 to-energy-blue-tint-1/20"
            : "bg-gradient-to-br from-white/10 to-white/5"
          : "bg-classic-blue/5 dark:bg-teal-chart p-2 rounded-none"
      }`}
    >
      {icon}
    </div>
    <div className={useDemoStyles ? "flex-1" : undefined}>
      <h3
        className={`${
          useDemoStyles
            ? `text-[11px] font-semibold uppercase tracking-widest mb-3 ${
                isSummary ? "text-energy-blue-tint-1" : "text-neutral-400"
              }`
            : "text-sm font-medium text-foreground mb-2"
        }`}
      >
        {title}
      </h3>
      <p
        className={`text-3xl font-bold ${
          useDemoStyles && forceDark ? "text-white" : "text-foreground"
        }`}
      >
        {value.toFixed(2)}
        <span
          className={`text-sm ml-1.5 font-semibold ${
            isSummary ? "text-energy-blue-tint-2" : "text-muted-foreground"
          }`}
        >
          {unit}
        </span>
      </p>
    </div>
  </div>
);

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

  // get available GPU IDs from metrics
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
    const rawGpuData = history.map((point) => {
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

    return stabilizeSingleZeroDropOptionalSeries(rawGpuData, [
      "compute",
      "render",
      "copy",
      "video",
      "videoEnhance",
    ]);
  }, [history, selectedGpu]);

  // determine which GPU engines are available (have at least one non-undefined value)
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

  // filter and prepare data for chart - only include available engines
  // and stabilize single zero drops to keep continuity like other GPU charts
  const gpuChartData = useMemo(() => {
    const normalizedGpuChartData: Array<{ timestamp: number } & Record<string, number>> =
      gpuData.map((point) => {
      const chartPoint: { timestamp: number } & Record<string, number> = {
        timestamp: point.timestamp,
      };

      availableEngines.forEach((engine) => {
        chartPoint[engine] =
          (point[engine as keyof typeof point] as number) ?? 0;
      });

      return chartPoint;
    });

    return stabilizeSingleZeroDropSeries(
      normalizedGpuChartData,
      availableEngines,
    );
  }, [gpuData, availableEngines]);
  const gpuFrequencyData = useMemo(() => {
    const gpuId = selectedGpu.toString();
    const rawGpuFrequencyData = history.map((point) => ({
      timestamp: point.timestamp,
      frequency: point.gpus[gpuId]?.frequency ?? 0,
    }));

    return stabilizeSingleZeroDropSeries(rawGpuFrequencyData, ["frequency"]);
  }, [history, selectedGpu]);

  const gpuPowerData = useMemo(() => {
    const gpuId = selectedGpu.toString();
    const rawGpuPowerData = history.map((point) => ({
      timestamp: point.timestamp,
      gpuPower: point.gpus[gpuId]?.gpuPower ?? 0,
      pkgPower: point.gpus[gpuId]?.pkgPower ?? 0,
    }));

    return stabilizeSingleZeroDropSeries(rawGpuPowerData, [
      "gpuPower",
      "pkgPower",
    ]);
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
        isSummary
          ? "p-4 rounded-xl border-2 border-energy-blue/40 bg-gradient-to-br from-energy-blue/5 to-energy-blue-tint-1/5 shadow-lg shadow-energy-blue/10"
          : ""
      }`}
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
          />
          <div
            className={`${
              useDemoStyles
                ? `${forceDark ? "bg-neutral-950/50" : "bg-card/80"}`
                : "bg-background"
            } ${useDemoStyles ? "rounded-xl shadow-2xl p-6" : "shadow-md p-4"} ${
              isSummary
                ? "border-2 border-energy-blue/40 shadow-energy-blue/20 ring-1 ring-energy-blue/20"
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
                      isSummary ? "text-energy-blue-tint-1" : "text-neutral-400"
                    }`
                  : "text-sm font-medium text-foreground mb-5"
              }`}
            >
              Power Usage Over Time
              {availableGpus.length > 1 && (
                <>
                  {" "}
                  <span className="inline-block min-w-[0.5rem]">
                    {selectedGpu}
                  </span>
                </>
              )}
            </h3>
            <div className="flex gap-4 items-stretch overflow-hidden">
              <div className="flex">
                <GpuSelector
                  availableGpus={availableGpus}
                  selectedGpu={selectedGpu}
                  onGpuChange={setSelectedGpu}
                />
              </div>
              <div className="flex-1 min-w-0">
                <MetricChart
                  title=""
                  data={gpuPowerData}
                  dataKeys={["gpuPower", "pkgPower"]}
                  colors={[
                    "var(--color-red-chart)",
                    "var(--color-yellow-chart)",
                  ]}
                  unit=" W"
                  yAxisDomain={[0, gpuPowerYAxisMax]}
                  showLegend={true}
                  className={`${useDemoStyles ? "!bg-transparent !border-0" : ""} !shadow-none !p-0`}
                  labels={["GPU Power", "Package Power"]}
                  maxDataPoints={CHART_MAX_DATA_POINTS}
                  isSummary={isSummary}
                  hideSummaryBorder={true}
                  forceDark={forceDark}
                  useDemoStyles={useDemoStyles}
                />
              </div>
            </div>
          </div>
          <div
            className={`${
              useDemoStyles
                ? `${forceDark ? "bg-neutral-950/50" : "bg-card/80"}`
                : "bg-background"
            } ${useDemoStyles ? "rounded-xl shadow-2xl p-6" : "shadow-md p-4"} ${
              isSummary
                ? "border-2 border-energy-blue/40 shadow-energy-blue/20 ring-1 ring-energy-blue/20"
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
                      isSummary ? "text-energy-blue-tint-1" : "text-neutral-400"
                    }`
                  : "text-sm font-medium text-foreground mb-5"
              }`}
            >
              GPU
              {availableGpus.length > 1 && (
                <>
                  {" "}
                  <span className="inline-block min-w-[0.5rem]">
                    {selectedGpu}
                  </span>
                </>
              )}{" "}
              Frequency Over Time
            </h3>
            <div className="flex gap-4 items-stretch overflow-hidden">
              <div className="flex">
                <GpuSelector
                  availableGpus={availableGpus}
                  selectedGpu={selectedGpu}
                  onGpuChange={setSelectedGpu}
                />
              </div>
              <div className="flex-1 min-w-0">
                <MetricChart
                  title=""
                  data={gpuFrequencyData}
                  dataKeys={["frequency"]}
                  colors={["var(--color-yellow-chart)"]}
                  unit=" GHz"
                  yAxisDomain={[0, gpuFrequencyYAxisMax]}
                  showLegend={false}
                  labels={["Frequency"]}
                  className={`${useDemoStyles ? "!bg-transparent !border-0" : ""} !shadow-none !p-0`}
                  maxDataPoints={CHART_MAX_DATA_POINTS}
                  isSummary={isSummary}
                  hideSummaryBorder={true}
                  forceDark={forceDark}
                  useDemoStyles={useDemoStyles}
                />
              </div>
            </div>
          </div>
          <div
            className={`${
              useDemoStyles
                ? `${forceDark ? "bg-neutral-950/50" : "bg-card/80"}`
                : "bg-background"
            } ${useDemoStyles ? "rounded-xl shadow-2xl p-6" : "shadow-md p-4"} ${
              isSummary
                ? "border-2 border-energy-blue/40 shadow-energy-blue/20 ring-1 ring-energy-blue/20"
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
                      isSummary ? "text-energy-blue-tint-1" : "text-neutral-400"
                    }`
                  : "text-sm font-medium text-foreground mb-5"
              }`}
            >
              GPU
              {availableGpus.length > 1 && (
                <>
                  {" "}
                  <span className="inline-block min-w-[0.5rem]">
                    {selectedGpu}
                  </span>
                </>
              )}{" "}
              Usage Over Time
            </h3>
            <div className="flex gap-4 items-stretch overflow-hidden">
              <div className="flex">
                <GpuSelector
                  availableGpus={availableGpus}
                  selectedGpu={selectedGpu}
                  onGpuChange={setSelectedGpu}
                />
              </div>
              <div className="flex-1 min-w-0">
                <MetricChart
                  title=""
                  data={gpuChartData}
                  dataKeys={availableEngines}
                  colors={availableEngines.map((e) => engineColors[e])}
                  unit="%"
                  yAxisDomain={[0, 100]}
                  labels={availableEngines.map((e) => engineLabels[e])}
                  wrapLegend={true}
                  className={`${useDemoStyles ? "!bg-transparent !border-0" : ""} !shadow-none !p-0`}
                  maxDataPoints={CHART_MAX_DATA_POINTS}
                  isSummary={isSummary}
                  hideSummaryBorder={true}
                  forceDark={forceDark}
                  useDemoStyles={useDemoStyles}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
