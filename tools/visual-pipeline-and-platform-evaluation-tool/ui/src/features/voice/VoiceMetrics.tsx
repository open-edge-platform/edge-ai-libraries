// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Clock, Timer } from "lucide-react";

export interface ConversionMetrics {
  requestMs: number;
  serviceMs: number | null;
}

function formatDuration(value: number | null): { value: string; unit: string } {
  if (value === null) return { value: "--", unit: "" };
  if (value >= 1000) return { value: (value / 1000).toFixed(2), unit: "s" };
  return { value: value.toFixed(2), unit: "ms" };
}

function DurationMetricCard({
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
      role="group"
      aria-label={title}
      className="flex min-h-24 items-center gap-3 bg-background p-4 shadow-md"
      title={description}
    >
      <span className="shrink-0 bg-classic-blue/5 p-2 dark:bg-teal-chart">
        {icon}
      </span>
      <div className="min-w-0">
        <h3 className="mb-2 text-sm font-medium text-foreground">{title}</h3>
        <p className="text-2xl font-bold text-foreground">
          {formatted.value}
          {formatted.unit && (
            <span className="ml-1.5 text-sm font-semibold text-muted-foreground">
              {formatted.unit}
            </span>
          )}
        </p>
      </div>
    </div>
  );
}

export function VoiceMetrics({
  label,
  metrics,
  className = "",
}: {
  label: string;
  metrics: ConversionMetrics | null;
  className?: string;
}) {
  return (
    <section
      aria-label={label}
      aria-live="polite"
      className={`min-w-0 space-y-4 ${className}`}
    >
      <div>
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <h2 className="mt-1 text-lg font-semibold">Performance</h2>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <DurationMetricCard
          title="Request duration"
          duration={metrics?.requestMs ?? null}
          icon={<Clock className="h-6 w-6 text-orange-chart" />}
          description="Browser request start through complete response processing"
        />
        <DurationMetricCard
          title="Service round trip"
          duration={metrics?.serviceMs ?? null}
          icon={<Timer className="h-6 w-6 text-green-chart" />}
          description="ViPPET backend to voice service through complete response receipt"
        />
      </div>
    </section>
  );
}
