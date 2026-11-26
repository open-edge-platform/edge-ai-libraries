// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { ChartId } from "./chartCatalog";
import { average, gpuMaxEngine, type FakePoint } from "./fakeMetrics";

export type DeviceId =
  | "pipeline"
  | "cpu"
  | "memory"
  | "gpu"
  | "npu"
  | "thermal";

export const DEVICE_LABELS: Record<DeviceId, string> = {
  pipeline: "Pipeline",
  cpu: "CPU",
  memory: "Memory",
  gpu: "GPU",
  npu: "NPU",
  thermal: "Thermal & Power",
};

export const DEVICE_CHARTS: Record<DeviceId, ChartId[]> = {
  pipeline: ["fps", "latency"],
  cpu: ["cpuUsage", "cpuFreq", "cpuTemp"],
  memory: ["memory"],
  gpu: ["gpuEngines", "gpuFreq", "gpuPower"],
  npu: ["npuUsage", "npuPower", "npuFreq"],
  thermal: ["cpuTemp", "power"],
};

export const GPU_ENGINES = [
  { key: "compute", label: "Compute", color: "var(--color-yellow-chart)" },
  { key: "render", label: "Render", color: "var(--color-orange-chart)" },
  { key: "copy", label: "Copy", color: "var(--color-purple-chart)" },
  { key: "video", label: "Video", color: "var(--color-red-chart)" },
  { key: "videoEnhance", label: "VE", color: "var(--color-geode-chart)" },
] as const;

/** Status colour for a 0–100 load; there is no warning token, so yellow-chart stands in. */
export const loadColor = (percent: number) =>
  percent >= 85
    ? "var(--color-destructive)"
    : percent >= 70
      ? "var(--color-yellow-chart)"
      : "var(--color-success)";

export const loadLabel = (percent: number) =>
  percent >= 85 ? "Critical" : percent >= 70 ? "High" : "Normal";

export type Insight = {
  id: string;
  severity: "critical" | "warning" | "info";
  device: Exclude<DeviceId, "thermal">;
  title: string;
  hint: string;
};

const SEVERITY_ORDER = { critical: 0, warning: 1, info: 2 } as const;

/**
 * Heuristic, frontend-only observations derived from metrics ViPPET already
 * collects. Thresholds are placeholders for a product decision.
 */
export const buildInsights = (
  history: FakePoint[],
  gpu: number,
  running: boolean,
): Insight[] => {
  const window = running ? history.slice(-10) : history;
  const avg = (fn: (p: FakePoint) => number) => average(window.map(fn));
  const gpuKey = String(gpu);
  const insights: Insight[] = [];

  const engines = GPU_ENGINES.map((e) => ({
    ...e,
    value: avg((p) => p.gpus[gpuKey]?.[e.key] ?? 0),
  })).sort((a, b) => b.value - a.value);
  const topEngine = engines[0];
  if (topEngine.value >= 70) {
    insights.push({
      id: "gpu-engine",
      severity: topEngine.value >= 85 ? "critical" : "warning",
      device: "gpu",
      title: `GPU ${gpu} ${topEngine.label} engine at ${topEngine.value.toFixed(0)}% — likely bottleneck`,
      hint: "Move a model to NPU or reduce the number of streams.",
    });
  }

  const npu = avg((p) => p.npu);
  if (npu < 20 && topEngine.value >= 70) {
    insights.push({
      id: "npu-idle",
      severity: "info",
      device: "npu",
      title: `NPU mostly idle (${npu.toFixed(0)}%)`,
      hint: "Offload classification (gvaclassify) to NPU to free the GPU.",
    });
  }

  const latencyAvg = avg((p) => p.latencyAvg);
  const latencyPeak = Math.max(...window.map((p) => p.latencyMax));
  if (latencyPeak > latencyAvg * 1.4) {
    insights.push({
      id: "latency-spikes",
      severity: "warning",
      device: "pipeline",
      title: `Latency spikes up to ${latencyPeak.toFixed(0)} ms (avg ${latencyAvg.toFixed(0)} ms)`,
      hint: "Spikes usually come from queue back-pressure; check queue sizes.",
    });
  }

  const recentFps = average(history.slice(-10).map((p) => p.fps));
  const runFps = average(history.map((p) => p.fps));
  if (recentFps < runFps * 0.9) {
    insights.push({
      id: "fps-drop",
      severity: "warning",
      device: "pipeline",
      title: `Frame rate dropped ${(100 - (recentFps / runFps) * 100).toFixed(0)}% in the last 10 s`,
      hint: "Check which device saturated at the same time.",
    });
  }

  const cpuTemp = avg((p) => p.cpuTemp);
  if (cpuTemp >= 75) {
    insights.push({
      id: "cpu-temp",
      severity: cpuTemp >= 85 ? "critical" : "warning",
      device: "cpu",
      title: `CPU temperature ${cpuTemp.toFixed(0)} °C`,
      hint: "Sustained heat can throttle CPU frequency and lower FPS.",
    });
  }

  const cpu = avg((p) => p.cpu);
  if (cpu >= 85) {
    insights.push({
      id: "cpu-load",
      severity: "warning",
      device: "cpu",
      title: `CPU usage ${cpu.toFixed(0)}%`,
      hint: "Decoding on CPU may limit FPS; try GPU decode (vah264dec).",
    });
  }

  const memory = avg((p) => p.memory);
  if (memory >= 85) {
    insights.push({
      id: "memory",
      severity: "warning",
      device: "memory",
      title: `Memory utilization ${memory.toFixed(0)}%`,
      hint: "Fewer streams or smaller models reduce memory pressure.",
    });
  }

  if (insights.length === 0) {
    insights.push({
      id: "ok",
      severity: "info",
      device: "pipeline",
      title: "All devices within normal range",
      hint: `GPU ${gpu} peak engine ${gpuMaxEngine(history.at(-1)?.gpus[gpuKey]).toFixed(0)}%.`,
    });
  }

  return insights.sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
  );
};

/** Current (running) or run-average (summary) value plus the full series. */
export const deviceStats = (
  history: FakePoint[],
  gpu: number,
  running: boolean,
) => {
  const gpuKey = String(gpu);
  const stat = (fn: (p: FakePoint) => number) => {
    const series = history.map(fn);
    return {
      value: running ? (series.at(-1) ?? 0) : average(series),
      min: Math.min(...series),
      max: Math.max(...series),
      series,
    };
  };

  return {
    fps: stat((p) => p.fps),
    latency: stat((p) => p.latencyAvg),
    latencyMin: stat((p) => p.latencyMin),
    latencyMax: stat((p) => p.latencyMax),
    cpu: stat((p) => p.cpu),
    cpuFreq: stat((p) => p.cpuFreq),
    cpuTemp: stat((p) => p.cpuTemp),
    memory: stat((p) => p.memory),
    gpu: stat((p) => gpuMaxEngine(p.gpus[gpuKey])),
    gpuFreq: stat((p) => p.gpus[gpuKey]?.frequency ?? 0),
    gpuPower: stat((p) => p.gpus[gpuKey]?.gpuPower ?? 0),
    pkgPower: stat((p) => p.gpus[gpuKey]?.pkgPower ?? 0),
    engines: GPU_ENGINES.map((e) => ({
      label: e.label,
      color: e.color,
      value: stat((p) => p.gpus[gpuKey]?.[e.key] ?? 0).value,
    })),
    npu: stat((p) => p.npu),
    npuPower: stat((p) => p.npuPower),
    npuFreq: stat((p) => p.npuFreq),
    totalPower: stat((p) => (p.gpus[gpuKey]?.pkgPower ?? 0) + p.npuPower),
  };
};

export type DeviceStats = ReturnType<typeof deviceStats>;
