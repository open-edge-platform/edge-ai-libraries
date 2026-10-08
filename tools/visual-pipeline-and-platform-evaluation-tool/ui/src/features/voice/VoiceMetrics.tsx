// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Activity, Clock, Timer } from "lucide-react";

export interface ConversionMetrics {
  requestMs: number;
  serviceMs: number | null;
}

export type VoiceMetricsState = "idle" | "running" | "success" | "error";

function formatDuration(value: number | null): { value: string; unit: string } {
  if (value === null) return { value: "--", unit: "" };
  if (value >= 1000) return { value: (value / 1000).toFixed(2), unit: "s" };
  return { value: value.toFixed(2), unit: "ms" };
}

const STATE_LABELS: Record<VoiceMetricsState, string> = {
  idle: "Awaiting conversion",
  running: "Processing",
  success: "Last successful conversion",
  error: "Conversion failed",
};

function MetricRow({
  title,
  duration,
  icon,
  description,
}: {
  title: string;
  duration: number | null;
  icon: React.ReactNode;
  description: string;
}) {
  const formatted = formatDuration(duration);
  return (
    <div
      className="flex min-h-24 items-center justify-between gap-4 py-4"
      title={description}
    >
      <div className="flex min-w-0 items-center gap-3">
        <span className="bg-classic-blue/5 p-2 dark:bg-teal-chart">{icon}</span>
        <h3 className="text-sm font-medium text-foreground">{title}</h3>
      </div>
      <p className="shrink-0 text-right text-2xl font-bold text-foreground">
        {formatted.value}
        {formatted.unit && (
          <span className="ml-1.5 text-sm font-semibold text-muted-foreground">
            {formatted.unit}
          </span>
        )}
      </p>
    </div>
  );
}

export function VoiceMetrics({
  label,
  metrics,
  state = metrics ? "success" : "idle",
  className = "",
}: {
  label: string;
  metrics: ConversionMetrics | null;
  state?: VoiceMetricsState;
  className?: string;
}) {
  return (
    <section
      aria-label={label}
      aria-live="polite"
      className={`min-w-0 bg-background p-4 shadow-sm sm:p-5 ${className}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          <h2 className="mt-1 text-lg font-semibold">Performance</h2>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-sm bg-muted px-2 py-1 text-xs text-muted-foreground">
          <Activity
            className={`size-3.5 ${state === "running" ? "animate-pulse" : ""}`}
          />
          {STATE_LABELS[state]}
        </span>
      </div>
      <div className="mt-4 divide-y border-y border-border">
        <MetricRow
          title="Request duration"
          duration={metrics?.requestMs ?? null}
          icon={<Clock className="h-6 w-6 text-orange-chart" />}
          description="Browser request start through complete response processing"
        />
        <MetricRow
          title="Service round trip"
          duration={metrics?.serviceMs ?? null}
          icon={<Timer className="h-6 w-6 text-green-chart" />}
          description="ViPPET backend to voice service through complete response receipt"
        />
      </div>
    </section>
  );
}
