// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useState, type ReactNode } from "react";
import { ChevronDown, Cpu, Gauge, Gpu, MemoryStick } from "lucide-react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { ChartById } from "./charts";
import {
  DEVICE_CHARTS,
  buildInsights,
  deviceStats,
  loadColor,
  type DeviceId,
} from "./devices";
import { MeterBars, RingGauge } from "./gauges";
import { InsightCounts, InsightList } from "./insightsUi";
import { FakeVideo, GpuToggle, RunStatusBadge, Sparkline } from "./shared";
import type { PanelProps } from "./types";

type RowProps = {
  id: DeviceId;
  icon: ReactNode;
  title: string;
  ring: { value: number; display: string; max?: number; color?: string };
  stats: { label: string; value: string }[];
  series: number[];
  color: string;
  extra?: ReactNode;
  action?: ReactNode;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
};

const DeviceRow = ({
  icon,
  title,
  ring,
  stats,
  series,
  color,
  extra,
  action,
  open,
  onToggle,
  children,
}: RowProps) => (
  <div className="border-b last:border-b-0">
    <div className="flex items-center gap-3 px-3 py-2.5">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex min-w-0 flex-1 items-center gap-3 text-left"
      >
        <RingGauge
          value={ring.value}
          max={ring.max}
          color={
            ring.color ?? loadColor((ring.value / (ring.max ?? 100)) * 100)
          }
          display={ring.display}
          size={52}
          thickness={5}
        />
        <span className="flex w-24 shrink-0 items-center gap-1.5 text-sm font-semibold">
          {icon}
          {title}
        </span>
        <span className="hidden min-w-0 flex-1 grid-cols-3 gap-2 @xl:grid">
          {stats.map((stat) => (
            <span key={stat.label} className="flex min-w-0 flex-col">
              <span className="truncate text-[0.625rem] uppercase tracking-widest text-muted-foreground">
                {stat.label}
              </span>
              <span className="truncate text-xs font-semibold tabular-nums">
                {stat.value}
              </span>
            </span>
          ))}
        </span>
        <Sparkline
          values={series}
          color={color}
          className="h-9 w-28 shrink-0 @3xl:w-40"
        />
        <ChevronDown
          className={cn(
            "size-4 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {action}
    </div>
    {extra && <div className="px-3 pb-3">{extra}</div>}
    {open && (
      <div className="grid grid-cols-1 gap-3 bg-muted/30 p-3 @3xl:grid-cols-2">
        {children}
      </div>
    )}
  </div>
);

/** Option E: insights banner + compact device rows that expand into charts. */
export const OptionEPanel = ({
  history,
  elapsed,
  running,
  gpu,
  setGpu,
}: PanelProps) => {
  const [open, setOpen] = useState<DeviceId | null>("gpu");
  const [showAllInsights, setShowAllInsights] = useState(false);
  const s = deviceStats(history, gpu, running);
  const insights = buildInsights(history, gpu, running);
  const toggle = (id: DeviceId) => setOpen((cur) => (cur === id ? null : id));
  const charts = (id: DeviceId) =>
    DEVICE_CHARTS[id].map((chartId) => (
      <ChartById
        key={chartId}
        id={chartId}
        history={history}
        gpu={gpu}
        isSummary={!running}
        compact
      />
    ));

  return (
    <div className="@container flex flex-col w-full h-full bg-background p-4 space-y-4 overflow-y-auto overflow-x-hidden min-w-0">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Test pipeline</h2>
        <RunStatusBadge running={running} elapsed={elapsed} />
      </div>

      <div className="grid grid-cols-1 gap-3 @3xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="min-w-0 overflow-hidden rounded-lg border shadow-xs">
          <div className="border-b bg-card px-3 py-1.5">
            <Tabs defaultValue="preview">
              <TabsList variant="line" className="h-8">
                <TabsTrigger value="preview">
                  {running ? "Live Preview" : "Output Video"}
                </TabsTrigger>
                <TabsTrigger value="metadata">Metadata JSON</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
          <FakeVideo tick={elapsed} live={running} />
        </div>
        <section className="flex min-w-0 flex-col rounded-lg border bg-card p-3 shadow-xs">
          <header className="flex items-center justify-between gap-2 pb-1">
            <h3 className="text-sm font-semibold">Insights</h3>
            <InsightCounts insights={insights} />
          </header>
          <InsightList
            insights={insights}
            onSelect={setOpen}
            limit={showAllInsights ? undefined : 3}
          />
          {insights.length > 3 && (
            <button
              type="button"
              onClick={() => setShowAllInsights((v) => !v)}
              className="mt-1 self-start text-xs font-medium text-brand-accent hover:underline"
            >
              {showAllInsights ? "Show less" : `Show all (${insights.length})`}
            </button>
          )}
        </section>
      </div>

      <div className="overflow-hidden rounded-lg border shadow-xs">
        <DeviceRow
          id="pipeline"
          icon={<Gauge className="size-4 text-magenta-chart" />}
          title="Pipeline"
          ring={{
            value: s.fps.value,
            max: Math.max(s.fps.max, 1),
            display: s.fps.value.toFixed(0),
            color: "var(--color-magenta-chart)",
          }}
          stats={[
            { label: "FPS", value: `${s.fps.value.toFixed(1)} fps` },
            { label: "Latency", value: `${s.latency.value.toFixed(1)} ms` },
            {
              label: "Lat. max",
              value: `${s.latencyMax.max.toFixed(0)} ms`,
            },
          ]}
          series={s.fps.series}
          color="var(--color-magenta-chart)"
          open={open === "pipeline"}
          onToggle={() => toggle("pipeline")}
        >
          {charts("pipeline")}
        </DeviceRow>
        <DeviceRow
          id="cpu"
          icon={<Cpu className="size-4 text-green-chart" />}
          title="CPU"
          ring={{ value: s.cpu.value, display: `${s.cpu.value.toFixed(0)}%` }}
          stats={[
            { label: "Usage", value: `${s.cpu.value.toFixed(1)}%` },
            { label: "Freq", value: `${s.cpuFreq.value.toFixed(2)} GHz` },
            { label: "Temp", value: `${s.cpuTemp.value.toFixed(0)} °C` },
          ]}
          series={s.cpu.series}
          color="var(--color-green-chart)"
          open={open === "cpu"}
          onToggle={() => toggle("cpu")}
        >
          {charts("cpu")}
        </DeviceRow>
        <DeviceRow
          id="gpu"
          icon={<Gpu className="size-4 text-yellow-chart" />}
          title={`GPU ${gpu}`}
          ring={{ value: s.gpu.value, display: `${s.gpu.value.toFixed(0)}%` }}
          stats={[
            { label: "Peak engine", value: `${s.gpu.value.toFixed(1)}%` },
            { label: "Freq", value: `${s.gpuFreq.value.toFixed(2)} GHz` },
            { label: "Power", value: `${s.gpuPower.value.toFixed(1)} W` },
          ]}
          series={s.gpu.series}
          color="var(--color-yellow-chart)"
          action={<GpuToggle gpu={gpu} onChange={setGpu} />}
          extra={<MeterBars items={s.engines} />}
          open={open === "gpu"}
          onToggle={() => toggle("gpu")}
        >
          {charts("gpu")}
        </DeviceRow>
        <DeviceRow
          id="npu"
          icon={<Gpu className="size-4 text-geode-chart" />}
          title="NPU"
          ring={{ value: s.npu.value, display: `${s.npu.value.toFixed(0)}%` }}
          stats={[
            { label: "Usage", value: `${s.npu.value.toFixed(1)}%` },
            { label: "Power", value: `${s.npuPower.value.toFixed(1)} W` },
            {
              label: "Freq",
              value: `${(s.npuFreq.value / 1000).toFixed(2)} GHz`,
            },
          ]}
          series={s.npu.series}
          color="var(--color-geode-chart)"
          open={open === "npu"}
          onToggle={() => toggle("npu")}
        >
          {charts("npu")}
        </DeviceRow>
        <DeviceRow
          id="memory"
          icon={<MemoryStick className="size-4 text-magenta-chart" />}
          title="Memory"
          ring={{
            value: s.memory.value,
            display: `${s.memory.value.toFixed(0)}%`,
          }}
          stats={[
            { label: "Used", value: `${s.memory.value.toFixed(1)}%` },
            { label: "Min", value: `${s.memory.min.toFixed(1)}%` },
            { label: "Max", value: `${s.memory.max.toFixed(1)}%` },
          ]}
          series={s.memory.series}
          color="var(--color-magenta-chart)"
          open={open === "memory"}
          onToggle={() => toggle("memory")}
        >
          {charts("memory")}
        </DeviceRow>
      </div>
    </div>
  );
};
