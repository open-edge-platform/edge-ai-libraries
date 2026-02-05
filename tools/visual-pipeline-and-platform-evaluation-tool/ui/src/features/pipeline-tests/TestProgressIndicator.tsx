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

interface MetricCardProps {
  title: string;
  value: number;
  unit: string;
  icon: React.ReactNode;
}

const MetricCard = ({ title, value, unit, icon }: MetricCardProps) => (
  <div className="bg-neutral-950/50 border border-neutral-800/50 rounded-xl shadow-2xl p-6 flex items-center space-x-4">
    <div className="shrink-0 p-3 bg-gradient-to-br from-white/10 to-white/5 rounded-lg backdrop-blur-sm">
      {icon}
    </div>
    <div className="flex-1">
      <h3 className="text-xs font-semibold text-neutral-400 uppercase tracking-widest mb-1">
        {title}
      </h3>
      <p className="text-3xl font-bold text-white">
        {value.toFixed(2)}
        <span className="text-sm text-neutral-500 ml-1.5 font-semibold">
          {unit}
        </span>
      </p>
    </div>
  </div>
);

interface TestProgressIndicatorProps {
  className?: string;
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

  const delayedFpsAverage = useMemo(() => {
    if (history.length === 0) return metrics.fps;
    const latestTimestamp = history[history.length - 1]?.timestamp ?? Date.now();
    const cutoffTimestamp = latestTimestamp - 7000;
    const values = history
      .filter((point) => point.timestamp <= cutoffTimestamp)
      .map((point) => point.fps ?? 0);

    if (values.length === 0) {
      const allValues = history.map((point) => point.fps ?? 0);
      return allValues.reduce((sum, value) => sum + value, 0) / allValues.length;
    }
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }, [history, metrics.fps]);

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

  // filter and prepare data for chart - only include available engines and replace undefined with 0
  const gpuChartData = useMemo(() => {
    return gpuData.map((point) => {
      const chartPoint: Record<string, number | undefined> & {
        timestamp: number;
      } = {
        timestamp: point.timestamp,
      };

      availableEngines.forEach((engine) => {
        chartPoint[engine] =
          (point[engine as keyof typeof point] as number) ?? 0;
      });

      return chartPoint;
    });
  }, [gpuData, availableEngines]);
  const gpuFrequencyData = useMemo(() => {
    const gpuId = selectedGpu.toString();
    return history.map((point) => ({
      timestamp: point.timestamp,
      frequency: point.gpus[gpuId]?.frequency ?? 0,
    }));
  }, [history, selectedGpu]);

  const gpuPowerData = useMemo(() => {
    const gpuId = selectedGpu.toString();
    return history.map((point) => ({
      timestamp: point.timestamp,
      gpuPower: point.gpus[gpuId]?.gpuPower ?? 0,
      pkgPower: point.gpus[gpuId]?.pkgPower ?? 0,
    }));
  }, [history, selectedGpu]);

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
    <div className={`space-y-4 ${className} text-foreground`}>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4">
        <div className="space-y-4">
          <MetricCard
            title={isSummary ? "Frame Rate Average" : "Frame Rate"}
            value={isSummary ? delayedFpsAverage : metrics.fps}
            unit="fps"
            icon={<Gauge className="h-6 w-6 text-magenta-chart" />}
          />
          <MetricChart
            title="Frame Rate Over Time"
            data={fpsData}
            dataKeys={["value"]}
            colors={["var(--color-magenta-chart)"]}
            unit=" fps"
            yAxisDomain={[0, Math.max(...fpsData.map((d) => d.value), 60)]}
            showLegend={false}
            labels={["Frame Rate"]}
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
          />
        </div>

        <div className="space-y-4">
          <MetricCard
            title={isSummary ? "CPU Usage Average" : "CPU Usage"}
            value={metrics.cpu}
            unit="%"
            icon={<Cpu className="h-6 w-6 text-green-chart" />}
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
          />
          <MetricChart
            title="CPU Temperature Over Time"
            data={cpuTempData}
            dataKeys={["temp"]}
            colors={["var(--color-green-chart)"]}
            unit="°C"
            yAxisDomain={[0, Math.max(...cpuTempData.map((d) => d.temp), 100)]}
            showLegend={false}
            labels={["Temperature"]}
          />
          <MetricChart
            title="CPU Frequency Over Time"
            data={cpuFrequencyData}
            dataKeys={["frequency"]}
            colors={["var(--color-green-chart)"]}
            unit=" GHz"
            yAxisDomain={[
              0,
              Math.max(...cpuFrequencyData.map((d) => d.frequency), 5),
            ]}
            showLegend={false}
            labels={["Frequency"]}
          />
        </div>

        <div className="space-y-4">
          <MetricCard
            title={isSummary ? "GPU Usage Average" : "GPU Usage"}
            value={(() => {
              const gpuMetrics =
                metrics.gpuDetailedMetrics[selectedGpu.toString()];
              if (!gpuMetrics) return 0;
              return Math.max(
                gpuMetrics.compute ?? 0,
                gpuMetrics.render ?? 0,
                gpuMetrics.copy ?? 0,
                gpuMetrics.video ?? 0,
                gpuMetrics.videoEnhance ?? 0,
              );
            })()}
            unit="%"
            icon={<Gpu className="h-6 w-6 text-yellow-chart" />}
          />
          <div className="bg-neutral-950/50 border border-neutral-800/50 rounded-xl shadow-2xl p-6">
            <h3 className="text-xs font-semibold text-neutral-400 uppercase tracking-widest mb-3">
              GPU
              {availableGpus.length > 1 && (
                <>
                  {" "}
                  <span className="inline-block min-w-[1ch]">
                    {selectedGpu}
                  </span>
                </>
              )}{" "}
              Usage Over Time
            </h3>
            <div className="flex gap-4 items-stretch -mt-3 overflow-hidden">
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
                  className="!shadow-none !p-0 !bg-transparent !border-0"
                  labels={availableEngines.map((e) => engineLabels[e])}
                />
              </div>
            </div>
          </div>
          <div className="bg-neutral-950/50 border border-neutral-800/50 rounded-xl shadow-2xl p-6">
            <h3 className="text-xs font-semibold text-neutral-400 uppercase tracking-widest mb-3">
              GPU
              {availableGpus.length > 1 && (
                <>
                  {" "}
                  <span className="inline-block min-w-[1ch]">
                    {selectedGpu}
                  </span>
                </>
              )}{" "}
              Frequency Over Time
            </h3>
            <div className="flex gap-4 items-stretch -mt-3 overflow-hidden">
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
                  yAxisDomain={[
                    0,
                    Math.max(...gpuFrequencyData.map((d) => d.frequency), 3),
                  ]}
                  showLegend={false}
                  labels={["Frequency"]}
                  className="!shadow-none !p-0 !bg-transparent !border-0"
                />
              </div>
            </div>
          </div>
          <div className="bg-neutral-950/50 border border-neutral-800/50 rounded-xl shadow-2xl p-6">
            <h3 className="text-xs font-semibold text-neutral-400 uppercase tracking-widest mb-3">
              GPU
              {availableGpus.length > 1 && (
                <>
                  {" "}
                  <span className="inline-block min-w-[1ch]">
                    {selectedGpu}
                  </span>
                </>
              )}{" "}
              Power Usage Over Time
            </h3>
            <div className="flex gap-4 items-stretch -mt-3 overflow-hidden">
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
                  yAxisDomain={[
                    0,
                    Math.max(
                      ...gpuPowerData.map((d) =>
                        Math.max(d.gpuPower, d.pkgPower),
                      ),
                      50,
                    ),
                  ]}
                  showLegend={true}
                  labels={["GPU Power", "Package Power"]}
                  className="!shadow-none !p-0 !bg-transparent !border-0"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
