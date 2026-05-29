// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { METRICS_URL } from "../../config";

type MetricValue = number | "N/A";

export const GPU_ENGINES = ["bcs", "rcs", "ccs", "vcs", "vecs"] as const;
export type GpuEngine = (typeof GPU_ENGINES)[number];

export type GpuMetricsPoint = Record<GpuEngine, MetricValue>;

export type MetricsPoint = {
  timestamp: string;
  cpu: MetricValue;
  gpu: GpuMetricsPoint;
  npu: MetricValue;
  ram: MetricValue;
};

const MAX_POINTS = 20;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function normalizeValue(value: unknown): MetricValue {
  if (typeof value === "number") {
    return value;
  }

  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : "N/A";
  }

  return "N/A";
}

function normalizeGpuMetrics(value: unknown): GpuMetricsPoint {
  const gpuValue = isRecord(value) ? value : {};

  return {
    bcs: normalizeValue(gpuValue.bcs),
    rcs: normalizeValue(gpuValue.rcs),
    ccs: normalizeValue(gpuValue.ccs),
    vcs: normalizeValue(gpuValue.vcs),
    vecs: normalizeValue(gpuValue.vecs),
  };
}

export function parseMetricsPoint(raw: Record<string, unknown>): MetricsPoint {
  return {
    timestamp: typeof raw.timestamp === "string" ? raw.timestamp : "",
    cpu: normalizeValue(raw.cpu),
    gpu: normalizeGpuMetrics(raw.gpu),
    npu: normalizeValue(raw.npu),
    ram: normalizeValue(raw.ram),
  };
}

export function useMetricsStream(ramType: "gb" | "percent" = "percent") {
  const [points, setPoints] = useState<MetricsPoint[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const url = `${METRICS_URL}?ram_type=${ramType}`;

    fetchEventSource(url, {
      method: "GET",
      signal: controller.signal,
      openWhenHidden: true,

      async onopen(response) {
        if (!response.ok) {
          throw new Error(`Metrics stream failed: ${response.status} ${response.statusText}`);
        }

        setIsConnected(true);
      },

      onmessage(event) {
        if (!event.data) {
          return;
        }

        const raw = JSON.parse(event.data) as unknown;
        if (!isRecord(raw)) {
          return;
        }

        const point = parseMetricsPoint(raw);

        setPoints((prev) => [...prev, point].slice(-MAX_POINTS));
      },

      onerror(error) {
        setIsConnected(false);
        console.error("Metrics stream error:", error);
        throw error;
      },
    });

    return () => {
      controller.abort();
      setIsConnected(false);
    };
  }, [ramType]);

  return { points, isConnected };
}
