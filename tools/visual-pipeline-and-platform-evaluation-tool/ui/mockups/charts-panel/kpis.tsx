// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Clock, Cpu, Gauge, Gpu, MemoryStick } from "lucide-react";
import { average, gpuMaxEngine, type FakePoint } from "./fakeMetrics";
import type { KpiTileProps } from "./shared";

export type DeviceTab = "overview" | "pipeline" | "cpu" | "gpu" | "npu";

export type Kpi = Omit<KpiTileProps, "active" | "onClick" | "summary"> & {
  id: string;
  tab: DeviceTab;
};

export const buildKpis = (
  history: FakePoint[],
  running: boolean,
  gpu: number,
): Kpi[] => {
  const pick = (fn: (p: FakePoint) => number) => {
    const values = history.map(fn);
    return { values, value: running ? (values.at(-1) ?? 0) : average(values) };
  };
  const iconClass = "size-3.5";

  return [
    {
      id: "fps",
      label: "Frame Rate",
      unit: "fps",
      color: "var(--color-magenta-chart)",
      icon: <Gauge className={`${iconClass} text-magenta-chart`} />,
      tab: "pipeline",
      ...pick((p) => p.fps),
    },
    {
      id: "latency",
      label: "Latency",
      unit: "ms",
      color: "var(--color-orange-chart)",
      icon: <Clock className={`${iconClass} text-orange-chart`} />,
      tab: "pipeline",
      ...pick((p) => p.latencyAvg),
    },
    {
      id: "cpu",
      label: "CPU",
      unit: "%",
      color: "var(--color-green-chart)",
      icon: <Cpu className={`${iconClass} text-green-chart`} />,
      tab: "cpu",
      ...pick((p) => p.cpu),
    },
    {
      id: "gpu",
      label: `GPU ${gpu}`,
      unit: "%",
      color: "var(--color-yellow-chart)",
      icon: <Gpu className={`${iconClass} text-yellow-chart`} />,
      tab: "gpu",
      ...pick((p) => gpuMaxEngine(p.gpus[String(gpu)])),
    },
    {
      id: "npu",
      label: "NPU",
      unit: "%",
      color: "var(--color-geode-chart)",
      icon: <Gpu className={`${iconClass} text-geode-chart`} />,
      tab: "npu",
      ...pick((p) => p.npu),
    },
    {
      id: "memory",
      label: "Memory",
      unit: "%",
      color: "var(--color-magenta-chart)",
      icon: <MemoryStick className={`${iconClass} text-magenta-chart`} />,
      tab: "cpu",
      ...pick((p) => p.memory),
    },
  ];
};
