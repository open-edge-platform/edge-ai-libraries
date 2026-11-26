// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export type ChartId =
  | "fps"
  | "latency"
  | "utilization"
  | "power"
  | "cpuUsage"
  | "cpuFreq"
  | "cpuTemp"
  | "memory"
  | "gpuEngines"
  | "gpuFreq"
  | "gpuPower"
  | "npuUsage"
  | "npuPower"
  | "npuFreq";

export const CHART_GROUPS: {
  group: string;
  items: { id: ChartId; label: string }[];
}[] = [
  {
    group: "Pipeline",
    items: [
      { id: "fps", label: "Frame Rate" },
      { id: "latency", label: "Latency" },
    ],
  },
  {
    group: "Overview",
    items: [
      { id: "utilization", label: "Utilization (all devices)" },
      { id: "power", label: "Power (all devices)" },
    ],
  },
  {
    group: "CPU & Memory",
    items: [
      { id: "cpuUsage", label: "CPU Usage" },
      { id: "cpuFreq", label: "CPU Frequency" },
      { id: "cpuTemp", label: "CPU Temperature" },
      { id: "memory", label: "Memory Utilization" },
    ],
  },
  {
    group: "GPU",
    items: [
      { id: "gpuEngines", label: "GPU Engine Usage" },
      { id: "gpuFreq", label: "GPU Frequency" },
      { id: "gpuPower", label: "GPU Power" },
    ],
  },
  {
    group: "NPU",
    items: [
      { id: "npuUsage", label: "NPU Usage" },
      { id: "npuPower", label: "NPU Power" },
      { id: "npuFreq", label: "NPU Frequency" },
    ],
  },
];

export const CHART_LABELS = Object.fromEntries(
  CHART_GROUPS.flatMap((g) => g.items.map((i) => [i.id, i.label])),
) as Record<ChartId, string>;
