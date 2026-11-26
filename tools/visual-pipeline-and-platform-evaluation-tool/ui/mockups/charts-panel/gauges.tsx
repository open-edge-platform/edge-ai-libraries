// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import { Maximize2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const RingGauge = ({
  value,
  max = 100,
  color,
  display,
  caption,
  size = 88,
  thickness = 8,
}: {
  value: number;
  max?: number;
  color: string;
  display: string;
  caption?: string;
  size?: number;
  thickness?: number;
}) => {
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  const ratio = Math.min(1, Math.max(0, value / max));

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={thickness}
          className="stroke-muted"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={thickness}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - ratio)}
          className="transition-[stroke-dashoffset] duration-700 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center leading-tight">
        <span
          className={cn(
            "font-bold tabular-nums",
            size >= 96
              ? "text-xl"
              : size >= 76
                ? "text-lg"
                : size >= 60
                  ? "text-sm"
                  : "text-xs",
          )}
        >
          {display}
        </span>
        {caption && (
          <span
            className={cn(
              "text-muted-foreground",
              size >= 76 ? "text-xs" : "text-[0.625rem]",
            )}
          >
            {caption}
          </span>
        )}
      </div>
    </div>
  );
};

export const StatRow = ({
  label,
  value,
  valueClassName,
}: {
  label: string;
  value: ReactNode;
  valueClassName?: string;
}) => (
  <div className="flex items-baseline justify-between gap-3 text-xs">
    <span className="text-muted-foreground">{label}</span>
    <span
      className={cn(
        "font-semibold tabular-nums text-foreground",
        valueClassName,
      )}
    >
      {value}
    </span>
  </div>
);

export const MeterBars = ({
  items,
}: {
  items: { label: string; value: number; color: string }[];
}) => (
  <div
    className="grid gap-2"
    style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}
  >
    {items.map((item) => (
      <div key={item.label} className="flex min-w-0 flex-col gap-1">
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full transition-[width] duration-700 ease-out"
            style={{ width: `${item.value}%`, backgroundColor: item.color }}
          />
        </div>
        <span className="flex justify-between gap-1 text-[0.625rem] text-muted-foreground">
          <span className="truncate">{item.label}</span>
          <span className="tabular-nums">{item.value.toFixed(0)}%</span>
        </span>
      </div>
    ))}
  </div>
);

export const CardShell = ({
  icon,
  title,
  action,
  onOpen,
  className,
  children,
}: {
  icon?: ReactNode;
  title: string;
  action?: ReactNode;
  onOpen?: () => void;
  className?: string;
  children: ReactNode;
}) => (
  <section
    className={cn(
      "flex min-w-0 flex-col gap-3 rounded-lg border bg-card p-4 shadow-xs",
      className,
    )}
  >
    <header className="flex items-center justify-between gap-2">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        {icon}
        {title}
      </h3>
      <div className="flex items-center gap-1">
        {action}
        {onOpen && (
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Open ${title} details`}
            onClick={onOpen}
          >
            <Maximize2 className="size-4" />
          </Button>
        )}
      </div>
    </header>
    {children}
  </section>
);
