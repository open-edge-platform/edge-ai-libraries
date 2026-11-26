// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Clock, Cpu, Gauge, Gpu } from "lucide-react";
import { MetricCard } from "@/features/metrics/MetricCard";
import {
  CpuFrequencyChart,
  CpuTemperatureChart,
  CpuUsageChart,
  FrameRateChart,
  GpuFrequencyChart,
  GpuPowerChart,
  GpuUsageChart,
  LatencyChart,
  MemoryUtilizationChart,
  NpuFrequencyChart,
  NpuPowerChart,
  NpuUsageChart,
} from "@/features/metrics/charts";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { GPU_IDS, average, gpuMaxEngine } from "./fakeMetrics";
import { FakeVideo } from "./shared";
import type { PanelProps } from "./types";

const ENGINE_KEYS = ["compute", "render", "copy", "video", "videoEnhance"];
const ENGINE_COLORS = [
  "var(--color-yellow-chart)",
  "var(--color-orange-chart)",
  "var(--color-purple-chart)",
  "var(--color-red-chart)",
  "var(--color-geode-chart)",
];
const ENGINE_LABELS = ["Compute", "Render", "Copy", "Video", "Video Enhance"];

/** Today's PerformanceTestPanel + MetricsDashboard layout, for comparison. */
export const CurrentPanel = ({
  history,
  elapsed,
  running,
  gpu,
  setGpu,
}: PanelProps) => {
  const isSummary = !running;
  const last = history.at(-1)!;
  const gpuKey = String(gpu);
  const max = (values: number[]) => Math.ceil(Math.max(1, ...values) * 1.15);

  const summaryClasses = {
    summaryCardClassName:
      "border-2 border-classic-blue/60 shadow-classic-blue/20 shadow-lg ring-2 ring-classic-blue/20 dark:border-energy-blue/60 dark:ring-energy-blue/30",
    summaryIconClassName:
      "bg-gradient-to-br from-classic-blue/15 to-classic-blue/25",
    summaryTitleClassName: "text-classic-blue dark:text-energy-blue-tint-1",
    summaryUnitClassName: "text-classic-blue dark:text-energy-blue-tint-2",
  };
  const summarySection = {
    summarySectionClassName:
      "border-2 border-classic-blue/40 shadow-classic-blue/20 ring-1 ring-classic-blue/20",
    summaryTitleClassName: "text-classic-blue",
  };

  const gpuData = history.map((p) => ({
    timestamp: p.timestamp,
    ...Object.fromEntries(
      ENGINE_KEYS.map((k) => [
        k,
        p.gpus[gpuKey]?.[k as keyof (typeof p.gpus)[string]] ?? 0,
      ]),
    ),
  }));

  return (
    <div className="flex flex-col w-full h-full bg-background p-4 space-y-4 overflow-y-auto overflow-x-hidden min-w-0">
      <h2 className="text-lg font-semibold">Test pipeline</h2>

      <Tabs value="media" className="flex flex-col min-w-0">
        <TabsList className="grid w-full grid-flow-col auto-cols-fr">
          <TabsTrigger value="media">Live Preview</TabsTrigger>
          <TabsTrigger value="metadata">Metadata JSON</TabsTrigger>
        </TabsList>
        <FakeVideo tick={elapsed} live={running} className="mt-2" />
      </Tabs>

      <div
        className={`space-y-4 text-foreground ${
          isSummary
            ? "p-4 border-2 border-classic-blue/40 bg-gradient-to-br from-classic-blue/5 to-classic-blue/10 shadow-lg shadow-classic-blue/10"
            : ""
        }`}
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <MetricCard
            title={isSummary ? "Frame Rate Average" : "Frame Rate"}
            value={isSummary ? average(history.map((p) => p.fps)) : last.fps}
            unit="fps"
            icon={<Gauge className="h-6 w-6 text-magenta-chart" />}
            isSummary={isSummary}
            {...summaryClasses}
          />
          {!isSummary && (
            <MetricCard
              title="CPU Usage"
              value={last.cpu}
              unit="%"
              icon={<Cpu className="h-6 w-6 text-green-chart" />}
            />
          )}
          {!isSummary && (
            <MetricCard
              title="GPU Usage"
              value={gpuMaxEngine(last.gpus[gpuKey])}
              unit="%"
              icon={<Gpu className="h-6 w-6 text-yellow-chart" />}
            />
          )}
          <MetricCard
            title={isSummary ? "Latency Average" : "Latency"}
            value={
              isSummary
                ? average(history.map((p) => p.latencyAvg))
                : last.latencyAvg
            }
            unit="ms"
            icon={<Clock className="h-6 w-6 text-orange-chart" />}
            isSummary={isSummary}
            {...summaryClasses}
          />
          {!isSummary && (
            <MetricCard
              title="NPU Usage"
              value={last.npu}
              unit="%"
              icon={<Gpu className="h-6 w-6 text-geode-chart" />}
            />
          )}
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FrameRateChart
            data={history.map((p) => ({
              timestamp: p.timestamp,
              value: p.fps,
            }))}
            yAxisMax={max(history.map((p) => p.fps))}
            isSummary={isSummary}
          />
          <CpuUsageChart
            data={history.map((p) => ({ timestamp: p.timestamp, user: p.cpu }))}
            isSummary={isSummary}
          />
          <MemoryUtilizationChart
            data={history.map((p) => ({
              timestamp: p.timestamp,
              memory: p.memory,
            }))}
            isSummary={isSummary}
          />
          <CpuTemperatureChart
            data={history.map((p) => ({
              timestamp: p.timestamp,
              temp: p.cpuTemp,
            }))}
            yAxisMax={max(history.map((p) => p.cpuTemp))}
            isSummary={isSummary}
          />
          <CpuFrequencyChart
            data={history.map((p) => ({
              timestamp: p.timestamp,
              frequency: Number(p.cpuFreq.toFixed(2)),
            }))}
            yAxisMax={max(history.map((p) => p.cpuFreq))}
            isSummary={isSummary}
          />
          <GpuUsageChart
            data={gpuData}
            dataKeys={ENGINE_KEYS}
            colors={ENGINE_COLORS}
            labels={ENGINE_LABELS}
            selectedGpu={gpu}
            availableGpus={GPU_IDS}
            onGpuChange={setGpu}
            isSummary={isSummary}
            {...summarySection}
          />
          <GpuPowerChart
            data={history.map((p) => ({
              timestamp: p.timestamp,
              gpuPower: p.gpus[gpuKey]?.gpuPower ?? 0,
              pkgPower: p.gpus[gpuKey]?.pkgPower ?? 0,
            }))}
            yAxisMax={max(history.map((p) => p.gpus[gpuKey]?.pkgPower ?? 0))}
            selectedGpu={gpu}
            availableGpus={GPU_IDS}
            onGpuChange={setGpu}
            isSummary={isSummary}
            {...summarySection}
          />
          <GpuFrequencyChart
            data={history.map((p) => ({
              timestamp: p.timestamp,
              frequency: Number((p.gpus[gpuKey]?.frequency ?? 0).toFixed(2)),
            }))}
            yAxisMax={3}
            selectedGpu={gpu}
            availableGpus={GPU_IDS}
            onGpuChange={setGpu}
            isSummary={isSummary}
            {...summarySection}
          />
          <NpuUsageChart
            data={history.map((p) => ({
              timestamp: p.timestamp,
              usage: p.npu,
            }))}
            isSummary={isSummary}
          />
          <NpuPowerChart
            data={history.map((p) => ({
              timestamp: p.timestamp,
              power: p.npuPower,
            }))}
            yAxisMax={max(history.map((p) => p.npuPower))}
            isSummary={isSummary}
          />
          <NpuFrequencyChart
            data={history.map((p) => ({
              timestamp: p.timestamp,
              frequency: Math.round(p.npuFreq),
            }))}
            yAxisMax={2000}
            isSummary={isSummary}
          />
          <LatencyChart
            data={history.map((p) => ({
              timestamp: p.timestamp,
              avg: p.latencyAvg,
              min: p.latencyMin,
              max: p.latencyMax,
            }))}
            yAxisMax={max(history.map((p) => p.latencyMax))}
            isSummary={isSummary}
          />
        </div>
      </div>
    </div>
  );
};
