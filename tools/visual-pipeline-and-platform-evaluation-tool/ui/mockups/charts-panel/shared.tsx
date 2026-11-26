// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import { Area, AreaChart, ResponsiveContainer, YAxis } from "recharts";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { GPU_IDS, formatElapsed } from "./fakeMetrics";

const DETECTIONS = [
  { label: "person 0.93", x: 18, y: 38, w: 10, h: 34, speed: 0.9 },
  { label: "person 0.88", x: 52, y: 42, w: 8, h: 28, speed: -0.6 },
  { label: "car 0.95", x: 66, y: 58, w: 22, h: 18, speed: 0.4 },
  { label: "bicycle 0.71", x: 33, y: 55, w: 11, h: 17, speed: 0.7 },
];

/** Stand-in for the WebRTC live preview. */
export const FakeVideo = ({
  tick,
  live,
  className,
}: {
  tick: number;
  live: boolean;
  className?: string;
}) => (
  <div
    className={cn(
      "relative aspect-video w-full overflow-hidden bg-neutral-900",
      className,
    )}
  >
    <div className="absolute inset-0 bg-[linear-gradient(180deg,#3b4a5a_0%,#5d6b78_45%,#2f3338_46%,#4a4f55_100%)]" />
    <div className="absolute inset-x-0 top-[46%] h-[2px] bg-white/10" />
    <div className="absolute left-[8%] top-[20%] h-[26%] w-[14%] bg-neutral-700/70" />
    <div className="absolute right-[6%] top-[14%] h-[32%] w-[18%] bg-neutral-600/60" />
    {DETECTIONS.map((d) => (
      <div
        key={d.label}
        className="absolute border-2 transition-[left] duration-1000 ease-linear"
        style={{
          left: `${d.x + Math.sin((tick * d.speed) / 6) * 4}%`,
          top: `${d.y}%`,
          width: `${d.w}%`,
          height: `${d.h}%`,
          borderColor: "var(--color-green-chart)",
        }}
      >
        <span
          className="absolute -top-5 left-[-2px] whitespace-nowrap px-1 text-[10px] font-semibold text-black"
          style={{ backgroundColor: "var(--color-green-chart)" }}
        >
          {d.label}
        </span>
      </div>
    ))}
    {live ? (
      <span className="absolute left-3 top-3 flex items-center gap-1.5 bg-red-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
        <span className="size-1.5 animate-pulse rounded-full bg-white" />
        Live
      </span>
    ) : (
      <span className="absolute left-3 top-3 bg-neutral-800/80 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white">
        Output video
      </span>
    )}
    <span className="absolute bottom-3 right-3 bg-black/60 px-2 py-0.5 font-mono text-[11px] text-white">
      1920×1080 · H.264
    </span>
  </div>
);

export const RunStatusBadge = ({
  running,
  elapsed,
}: {
  running: boolean;
  elapsed: number;
}) =>
  running ? (
    <Badge variant="outline" className="gap-1.5 font-medium">
      <span className="size-2 animate-pulse rounded-full bg-success" />
      Running · {formatElapsed(elapsed)}
    </Badge>
  ) : (
    <Badge variant="outline" className="gap-1.5 font-medium text-brand-accent">
      <span className="size-2 rounded-full bg-brand-accent" />
      Run summary · {formatElapsed(elapsed)}
    </Badge>
  );

export const Sparkline = ({
  values,
  color,
  className,
}: {
  values: number[];
  color: string;
  className?: string;
}) => (
  <div className={cn("h-8 w-full", className)}>
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={values.map((value, i) => ({ i, value }))}>
        <YAxis hide domain={["dataMin - 2", "dataMax + 2"]} />
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          fill={color}
          fillOpacity={0.2}
          strokeWidth={1.5}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  </div>
);

export type KpiTileProps = {
  label: string;
  value: number;
  unit: string;
  color: string;
  icon?: ReactNode;
  values?: number[];
  active?: boolean;
  summary?: boolean;
  decimals?: number;
  onClick?: () => void;
};

export const KpiTile = ({
  label,
  value,
  unit,
  color,
  icon,
  values,
  active = false,
  summary = false,
  decimals = 1,
  onClick,
}: KpiTileProps) => (
  <button
    type="button"
    onClick={onClick}
    className={cn(
      "flex min-w-0 flex-col gap-1 border bg-background p-3 text-left shadow-sm transition-colors",
      onClick && "hover:bg-accent/40",
      active
        ? "border-brand-accent ring-1 ring-brand-accent/40"
        : "border-border",
    )}
  >
    <span className="flex items-center gap-1.5 text-[0.625rem] font-semibold uppercase tracking-widest text-muted-foreground">
      {icon}
      <span className="truncate">
        {label}
        {summary && " · avg"}
      </span>
    </span>
    <span className="text-xl font-bold tabular-nums text-foreground">
      {value.toFixed(decimals)}
      <span className="ml-1 text-xs font-semibold text-muted-foreground">
        {unit}
      </span>
    </span>
    {values && <Sparkline values={values} color={color} />}
  </button>
);

export const GpuToggle = ({
  gpu,
  onChange,
}: {
  gpu: number;
  onChange: (gpu: number) => void;
}) => (
  <div className="inline-flex h-8 items-center bg-muted p-[0.1875rem]">
    {GPU_IDS.map((id) => (
      <button
        key={id}
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          onChange(id);
        }}
        className={cn(
          "h-full px-3 text-xs font-medium transition-colors",
          gpu === id
            ? "bg-background text-foreground shadow-sm"
            : "text-foreground/60 hover:text-foreground",
        )}
      >
        GPU {id}
      </button>
    ))}
  </div>
);

export const PanelTitle = ({ children }: { children: ReactNode }) => (
  <div className="flex items-center justify-between gap-2">{children}</div>
);
