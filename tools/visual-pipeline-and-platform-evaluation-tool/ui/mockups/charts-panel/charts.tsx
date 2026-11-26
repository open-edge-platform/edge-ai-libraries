// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { MetricChart } from "@/features/metrics/MetricChart";
import { getRecentYAxisMax } from "@/features/metrics/charts";
import type { ChartId } from "./chartCatalog";
import { MAX_POINTS, gpuMaxEngine, type FakePoint } from "./fakeMetrics";

const ENGINES = [
  { key: "compute", label: "Compute", color: "var(--color-yellow-chart)" },
  { key: "render", label: "Render", color: "var(--color-orange-chart)" },
  { key: "copy", label: "Copy", color: "var(--color-purple-chart)" },
  { key: "video", label: "Video", color: "var(--color-red-chart)" },
  {
    key: "videoEnhance",
    label: "Video Enhance",
    color: "var(--color-geode-chart)",
  },
] as const;

type ChartByIdProps = {
  id: ChartId;
  history: FakePoint[];
  gpu: number;
  isSummary?: boolean;
  compact?: boolean;
  hideTitle?: boolean;
  className?: string;
  help?: { label: string; description: string }[];
};

const yMax = (values: number[], minMax: number) =>
  Math.ceil(getRecentYAxisMax(values, MAX_POINTS, minMax) * 1.15);

export const ChartById = ({
  id,
  history,
  gpu,
  isSummary = false,
  compact = false,
  hideTitle = false,
  className = "",
  help,
}: ChartByIdProps) => {
  const gpuKey = String(gpu);
  const common = {
    maxDataPoints: MAX_POINTS,
    isSummary,
    className: `${compact ? "!h-auto" : ""} ${className}`,
    titleTooltip: help,
  };
  const title = (text: string) => (hideTitle ? " " : text);

  switch (id) {
    case "fps":
      return (
        <MetricChart
          {...common}
          title={title("Frame Rate Over Time")}
          data={history.map((p) => ({ timestamp: p.timestamp, value: p.fps }))}
          dataKeys={["value"]}
          colors={["var(--color-magenta-chart)"]}
          labels={["Frame Rate"]}
          unit=" fps"
          showLegend={false}
          yAxisDomain={[
            0,
            yMax(
              history.map((p) => p.fps),
              1,
            ),
          ]}
        />
      );
    case "latency":
      return (
        <MetricChart
          {...common}
          title={title("Latency Over Time")}
          data={history.map((p) => ({
            timestamp: p.timestamp,
            avg: p.latencyAvg,
            min: p.latencyMin,
            max: p.latencyMax,
          }))}
          dataKeys={["avg", "min", "max"]}
          colors={[
            "var(--color-orange-chart)",
            "var(--color-green-chart)",
            "var(--color-red-chart)",
          ]}
          labels={["Avg", "Min", "Max"]}
          unit=" ms"
          showLegend={!compact}
          yAxisDomain={[
            0,
            yMax(
              history.map((p) => p.latencyMax),
              1,
            ),
          ]}
        />
      );
    case "utilization":
      return (
        <MetricChart
          {...common}
          title={title("Utilization Over Time")}
          data={history.map((p) => ({
            timestamp: p.timestamp,
            cpu: p.cpu,
            gpu: gpuMaxEngine(p.gpus[gpuKey]),
            npu: p.npu,
            memory: p.memory,
          }))}
          dataKeys={["cpu", "gpu", "npu", "memory"]}
          colors={[
            "var(--color-green-chart)",
            "var(--color-yellow-chart)",
            "var(--color-geode-chart)",
            "var(--color-magenta-chart)",
          ]}
          labels={["CPU", `GPU ${gpu}`, "NPU", "Memory"]}
          unit="%"
          showLegend
          yAxisDomain={[0, 100]}
        />
      );
    case "power":
      return (
        <MetricChart
          {...common}
          title={title("Power Over Time")}
          data={history.map((p) => ({
            timestamp: p.timestamp,
            gpuPower: p.gpus[gpuKey]?.gpuPower ?? 0,
            pkgPower: p.gpus[gpuKey]?.pkgPower ?? 0,
            npuPower: p.npuPower,
          }))}
          dataKeys={["gpuPower", "pkgPower", "npuPower"]}
          colors={[
            "var(--color-red-chart)",
            "var(--color-yellow-chart)",
            "var(--color-orange-chart)",
          ]}
          labels={[`GPU ${gpu}`, "Package", "NPU"]}
          unit=" W"
          showLegend={!compact}
          yAxisDomain={[
            0,
            yMax(
              history.map((p) => p.gpus[gpuKey]?.pkgPower ?? 0),
              1,
            ),
          ]}
        />
      );
    case "cpuUsage":
      return (
        <MetricChart
          {...common}
          title={title("CPU Usage Over Time")}
          data={history.map((p) => ({ timestamp: p.timestamp, user: p.cpu }))}
          dataKeys={["user"]}
          colors={["var(--color-green-chart)"]}
          labels={["CPU Usage"]}
          unit="%"
          showLegend={false}
          yAxisDomain={[0, 100]}
        />
      );
    case "cpuFreq":
      return (
        <MetricChart
          {...common}
          title={title("CPU Frequency Over Time")}
          data={history.map((p) => ({
            timestamp: p.timestamp,
            frequency: Number(p.cpuFreq.toFixed(2)),
          }))}
          dataKeys={["frequency"]}
          colors={["var(--color-green-chart)"]}
          labels={["Frequency"]}
          unit=" GHz"
          showLegend={false}
          yAxisDomain={[
            0,
            yMax(
              history.map((p) => p.cpuFreq),
              1,
            ),
          ]}
        />
      );
    case "cpuTemp":
      return (
        <MetricChart
          {...common}
          title={title("CPU Temperature Over Time")}
          data={history.map((p) => ({
            timestamp: p.timestamp,
            temp: p.cpuTemp,
          }))}
          dataKeys={["temp"]}
          colors={["var(--color-green-chart)"]}
          labels={["Temperature"]}
          unit="°C"
          showLegend={false}
          yAxisDomain={[
            0,
            yMax(
              history.map((p) => p.cpuTemp),
              1,
            ),
          ]}
        />
      );
    case "memory":
      return (
        <MetricChart
          {...common}
          title={title("Memory Utilization Over Time")}
          data={history.map((p) => ({
            timestamp: p.timestamp,
            memory: p.memory,
          }))}
          dataKeys={["memory"]}
          colors={["var(--color-magenta-chart)"]}
          labels={["Memory"]}
          unit="%"
          showLegend={false}
          yAxisDomain={[0, 100]}
        />
      );
    case "gpuEngines":
      return (
        <MetricChart
          {...common}
          title={title(`GPU ${gpu} Engine Usage Over Time`)}
          data={history.map((p) => ({
            timestamp: p.timestamp,
            ...Object.fromEntries(
              ENGINES.map((e) => [e.key, p.gpus[gpuKey]?.[e.key] ?? 0]),
            ),
          }))}
          dataKeys={ENGINES.map((e) => e.key)}
          colors={ENGINES.map((e) => e.color)}
          labels={ENGINES.map((e) => e.label)}
          unit="%"
          showLegend
          wrapLegend
          yAxisDomain={[0, 100]}
        />
      );
    case "gpuFreq":
      return (
        <MetricChart
          {...common}
          title={title(`GPU ${gpu} Frequency Over Time`)}
          data={history.map((p) => ({
            timestamp: p.timestamp,
            frequency: Number((p.gpus[gpuKey]?.frequency ?? 0).toFixed(2)),
          }))}
          dataKeys={["frequency"]}
          colors={["var(--color-yellow-chart)"]}
          labels={["Frequency"]}
          unit=" GHz"
          showLegend={false}
          yAxisDomain={[0, 3]}
        />
      );
    case "gpuPower":
      return (
        <MetricChart
          {...common}
          title={title(`GPU ${gpu} Power Over Time`)}
          data={history.map((p) => ({
            timestamp: p.timestamp,
            gpuPower: p.gpus[gpuKey]?.gpuPower ?? 0,
            pkgPower: p.gpus[gpuKey]?.pkgPower ?? 0,
          }))}
          dataKeys={["gpuPower", "pkgPower"]}
          colors={["var(--color-red-chart)", "var(--color-yellow-chart)"]}
          labels={["GPU Power", "Package Power"]}
          unit=" W"
          showLegend={!compact}
          yAxisDomain={[
            0,
            yMax(
              history.map((p) => p.gpus[gpuKey]?.pkgPower ?? 0),
              1,
            ),
          ]}
        />
      );
    case "npuUsage":
      return (
        <MetricChart
          {...common}
          title={title("NPU Usage Over Time")}
          data={history.map((p) => ({ timestamp: p.timestamp, usage: p.npu }))}
          dataKeys={["usage"]}
          colors={["var(--color-geode-chart)"]}
          labels={["NPU Usage"]}
          unit="%"
          showLegend={false}
          yAxisDomain={[0, 100]}
        />
      );
    case "npuPower":
      return (
        <MetricChart
          {...common}
          title={title("NPU Power Over Time")}
          data={history.map((p) => ({
            timestamp: p.timestamp,
            power: p.npuPower,
          }))}
          dataKeys={["power"]}
          colors={["var(--color-orange-chart)"]}
          labels={["Power"]}
          unit=" W"
          showLegend={false}
          yAxisDomain={[
            0,
            yMax(
              history.map((p) => p.npuPower),
              1,
            ),
          ]}
        />
      );
    case "npuFreq":
      return (
        <MetricChart
          {...common}
          title={title("NPU Frequency Over Time")}
          data={history.map((p) => ({
            timestamp: p.timestamp,
            frequency: Math.round(p.npuFreq),
          }))}
          dataKeys={["frequency"]}
          colors={["var(--color-purple-chart)"]}
          labels={["Frequency"]}
          unit=" MHz"
          showLegend={false}
          yAxisDomain={[0, 2000]}
        />
      );
  }
};
