// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";

export type FakeGpuPoint = {
  compute: number;
  render: number;
  copy: number;
  video: number;
  videoEnhance: number;
  frequency: number;
  gpuPower: number;
  pkgPower: number;
};

export type FakePoint = {
  timestamp: number;
  fps: number;
  latencyAvg: number;
  latencyMin: number;
  latencyMax: number;
  cpu: number;
  cpuTemp: number;
  cpuFreq: number;
  memory: number;
  gpus: Record<string, FakeGpuPoint>;
  npu: number;
  npuPower: number;
  npuFreq: number;
};

export const MAX_POINTS = 56;
export const GPU_IDS = [0, 1];

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

const drift = (
  prev: number,
  target: number,
  spread: number,
  min: number,
  max: number,
) =>
  clamp(
    prev + (target - prev) * 0.25 + (Math.random() - 0.5) * spread,
    min,
    max,
  );

const nextGpu = (
  prev: FakeGpuPoint | undefined,
  load: number,
): FakeGpuPoint => ({
  compute: drift(prev?.compute ?? 60 * load, 70 * load, 10, 0, 100),
  render: drift(prev?.render ?? 20 * load, 25 * load, 6, 0, 100),
  copy: drift(prev?.copy ?? 8 * load, 10 * load, 4, 0, 100),
  video: drift(prev?.video ?? 40 * load, 45 * load, 8, 0, 100),
  videoEnhance: drift(prev?.videoEnhance ?? 15 * load, 18 * load, 5, 0, 100),
  frequency: drift(prev?.frequency ?? 1.8 * load, 2.0 * load, 0.15, 0.3, 2.4),
  gpuPower: drift(prev?.gpuPower ?? 22 * load, 24 * load, 3, 1, 60),
  pkgPower: drift(prev?.pkgPower ?? 38 * load, 40 * load, 3, 5, 80),
});

const nextPoint = (
  prev: FakePoint | undefined,
  timestamp: number,
): FakePoint => {
  const fps = drift(prev?.fps ?? 29, 30, 2.5, 18, 32);
  const latencyAvg = drift(prev?.latencyAvg ?? 33, 34, 4, 20, 60);
  return {
    timestamp,
    fps,
    latencyAvg,
    latencyMin: Math.max(10, latencyAvg - 6 - Math.random() * 4),
    latencyMax: latencyAvg + 8 + Math.random() * 10,
    cpu: drift(prev?.cpu ?? 45, 48, 8, 5, 100),
    cpuTemp: drift(prev?.cpuTemp ?? 62, 64, 1.5, 40, 95),
    cpuFreq: drift(prev?.cpuFreq ?? 3.2, 3.3, 0.2, 1.2, 4.8),
    memory: drift(prev?.memory ?? 58, 59, 1, 20, 95),
    gpus: {
      "0": nextGpu(prev?.gpus["0"], 1),
      "1": nextGpu(prev?.gpus["1"], 0.35),
    },
    npu: drift(prev?.npu ?? 12, 14, 4, 0, 100),
    npuPower: drift(prev?.npuPower ?? 4, 4.2, 0.6, 0.5, 15),
    npuFreq: drift(prev?.npuFreq ?? 1400, 1450, 60, 600, 1950),
  };
};

const seedHistory = (): FakePoint[] => {
  const now = Date.now();
  const points: FakePoint[] = [];
  for (let i = 42; i > 0; i--) {
    points.push(nextPoint(points.at(-1), now - i * 1000));
  }
  return points;
};

/** Random-walk metrics ticking once per second; frozen = run finished. */
export const useFakeMetrics = (frozen: boolean) => {
  const [history, setHistory] = useState<FakePoint[]>(seedHistory);
  const [elapsed, setElapsed] = useState(42);

  useEffect(() => {
    if (frozen) return;
    const timer = window.setInterval(() => {
      setHistory((prev) => [
        ...prev.slice(-(MAX_POINTS - 1)),
        nextPoint(prev.at(-1), Date.now()),
      ]);
      setElapsed((prev) => prev + 1);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [frozen]);

  return { history, elapsed };
};

export const average = (values: number[]) =>
  values.length === 0 ? 0 : values.reduce((a, b) => a + b, 0) / values.length;

export const gpuMaxEngine = (gpu: FakeGpuPoint | undefined) =>
  gpu
    ? Math.max(gpu.compute, gpu.render, gpu.copy, gpu.video, gpu.videoEnhance)
    : 0;

export const formatElapsed = (seconds: number) => {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
};
