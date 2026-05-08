// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { METRICS_URL } from "../../config";

type MetricValue = number | "N/A";

export type MetricsPoint = {
  timestamp: string;
  cpu: MetricValue;
  gpu: MetricValue;
  npu: MetricValue;
  ram: MetricValue;
};

const MAX_POINTS = 20;

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

        const raw = JSON.parse(event.data);

        const point: MetricsPoint = {
          timestamp: raw.timestamp,
          cpu: normalizeValue(raw.cpu),
          gpu: normalizeValue(raw.gpu),
          npu: normalizeValue(raw.npu),
          ram: normalizeValue(raw.ram),
        };

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