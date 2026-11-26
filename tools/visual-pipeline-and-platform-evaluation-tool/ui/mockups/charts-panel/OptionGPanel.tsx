// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { Info } from "lucide-react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { CHART_LABELS, type ChartId } from "./chartCatalog";
import { ChartById } from "./charts";
import {
  buildInsights,
  deviceStats,
  loadColor,
  loadLabel,
  type DeviceStats,
} from "./devices";
import { RingGauge } from "./gauges";
import { SeverityIcon } from "./insightsUi";
import { CHART_HELP, TILE_HELP, TONE_COLOR, type TileId } from "./metricInfo";
import { FakeVideo, GpuToggle, RunStatusBadge } from "./shared";
import type { PanelProps } from "./types";

type FocusId = "overview" | "pipeline" | "cpu" | "gpu" | "npu" | "memory";

/** First chart is shown large, the rest as compact sub-charts below it. */
const FOCUS: { id: FocusId; label: string; charts: ChartId[] }[] = [
  {
    id: "overview",
    label: "Overview",
    charts: ["utilization", "power", "cpuTemp"],
  },
  { id: "pipeline", label: "Pipeline", charts: ["fps", "latency"] },
  { id: "cpu", label: "CPU", charts: ["cpuUsage", "cpuTemp", "cpuFreq"] },
  { id: "gpu", label: "GPU", charts: ["gpuEngines", "gpuFreq", "gpuPower"] },
  { id: "npu", label: "NPU", charts: ["npuUsage", "npuPower", "npuFreq"] },
  { id: "memory", label: "Memory", charts: ["memory"] },
];

type TileData = {
  id: TileId;
  focus: FocusId;
  label: string;
  ring: number;
  max?: number;
  color?: string;
  display: string;
  primary: string;
  range: string;
  /** Load percent for the status pill; omitted for non-utilization metrics. */
  load?: number;
};

const StatusPill = ({ percent }: { percent: number }) => {
  const color = loadColor(percent);
  return (
    <span
      className="shrink-0 rounded-full px-1.5 py-px text-[0.625rem] font-semibold"
      style={{
        backgroundColor: `color-mix(in oklch, ${color} 14%, transparent)`,
        color: `color-mix(in oklch, ${color} 80%, var(--foreground))`,
      }}
    >
      {loadLabel(percent)}
    </span>
  );
};

const TileInfo = ({ id, stats }: { id: TileId; stats: DeviceStats }) => {
  const help = TILE_HELP[id];
  const reading = help.read(stats);
  const color = TONE_COLOR[reading.tone];
  const flagged = reading.tone === "warn" || reading.tone === "bad";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          role="img"
          aria-label={`About ${help.title}`}
          tabIndex={0}
          onClick={(event) => event.stopPropagation()}
          className="absolute right-1.5 top-1.5 rounded-full p-0.5 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          style={flagged ? { color } : undefined}
        >
          <Info className="size-3.5" />
        </span>
      </TooltipTrigger>
      <TooltipContent side="left" align="start" className="max-w-sm">
        <div className="space-y-2 py-1">
          <p className="font-semibold">{help.title}</p>
          <p>{help.what}</p>
          {help.scale && <p className="text-muted-foreground">{help.scale}</p>}
          <div className="flex gap-2 border-t pt-2">
            <span
              className="mt-1 size-2 shrink-0 rounded-full"
              style={{ backgroundColor: color }}
            />
            <p>
              <span className="font-semibold">Right now: </span>
              {reading.text}
            </p>
          </div>
        </div>
      </TooltipContent>
    </Tooltip>
  );
};

const ChartInfo = ({ id }: { id: ChartId }) => (
  <Tooltip>
    <TooltipTrigger asChild>
      <button
        type="button"
        aria-label={`About ${CHART_LABELS[id]}`}
        className="text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Info className="size-4" />
      </button>
    </TooltipTrigger>
    <TooltipContent side="top" align="end" className="max-w-sm">
      <div className="space-y-1.5">
        {CHART_HELP[id].map((item) => (
          <p key={item.label}>
            <span className="font-semibold">{item.label}:</span>{" "}
            {item.description}
          </p>
        ))}
      </div>
    </TooltipContent>
  </Tooltip>
);

/** Option G: option F plus hover explanations of what each metric means. */
export const OptionGPanel = ({
  history,
  elapsed,
  running,
  gpu,
  setGpu,
}: PanelProps) => {
  const [focus, setFocus] = useState<FocusId>("overview");
  const s = deviceStats(history, gpu, running);
  const insights = buildInsights(history, gpu, running);
  const focused = FOCUS.find((f) => f.id === focus)!;

  const tiles: TileData[] = [
    {
      id: "fps",
      focus: "pipeline",
      label: "Frame rate",
      ring: s.fps.value,
      max: Math.max(s.fps.max, 1),
      color: "var(--color-magenta-chart)",
      display: s.fps.value.toFixed(1),
      primary: "fps",
      range: `min ${s.fps.min.toFixed(1)} · max ${s.fps.max.toFixed(1)}`,
    },
    {
      id: "latency",
      focus: "pipeline",
      label: "Latency",
      ring: s.latency.value,
      max: Math.max(s.latencyMax.max, 1),
      color: "var(--color-orange-chart)",
      display: s.latency.value.toFixed(0),
      primary: "ms avg",
      range: `min ${s.latencyMin.min.toFixed(0)} · max ${s.latencyMax.max.toFixed(0)} ms`,
    },
    {
      id: "cpu",
      focus: "cpu",
      label: "CPU",
      ring: s.cpu.value,
      display: `${s.cpu.value.toFixed(0)}%`,
      primary: `${s.cpuFreq.value.toFixed(2)} GHz · ${s.cpuTemp.value.toFixed(0)}°C`,
      range: `min ${s.cpu.min.toFixed(0)}% · max ${s.cpu.max.toFixed(0)}%`,
      load: s.cpu.value,
    },
    {
      id: "gpu",
      focus: "gpu",
      label: `GPU ${gpu}`,
      ring: s.gpu.value,
      display: `${s.gpu.value.toFixed(0)}%`,
      primary: `${s.gpuFreq.value.toFixed(2)} GHz · ${s.gpuPower.value.toFixed(0)} W`,
      range: `min ${s.gpu.min.toFixed(0)}% · max ${s.gpu.max.toFixed(0)}%`,
      load: s.gpu.value,
    },
    {
      id: "npu",
      focus: "npu",
      label: "NPU",
      ring: s.npu.value,
      display: `${s.npu.value.toFixed(0)}%`,
      primary: `${s.npuPower.value.toFixed(1)} W · ${(s.npuFreq.value / 1000).toFixed(2)} GHz`,
      range: `min ${s.npu.min.toFixed(0)}% · max ${s.npu.max.toFixed(0)}%`,
      load: s.npu.value,
    },
    {
      id: "memory",
      focus: "memory",
      label: "Memory",
      ring: s.memory.value,
      display: `${s.memory.value.toFixed(0)}%`,
      primary: "used",
      range: `min ${s.memory.min.toFixed(0)}% · max ${s.memory.max.toFixed(0)}%`,
      load: s.memory.value,
    },
  ];

  return (
    <div className="@container flex flex-col w-full h-full bg-background p-4 space-y-4 overflow-y-auto overflow-x-hidden min-w-0">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Test pipeline</h2>
        <RunStatusBadge running={running} elapsed={elapsed} />
      </div>

      <div className="flex shrink-0 gap-2 overflow-x-auto pb-1">
        {insights.map((insight) => (
          <span
            key={insight.id}
            title={insight.hint}
            className="flex shrink-0 items-center gap-1.5 rounded-full border bg-card px-3 py-1 text-xs"
          >
            <SeverityIcon severity={insight.severity} className="size-3.5" />
            {insight.title}
          </span>
        ))}
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

        <div className="grid grid-cols-2 gap-2 @xl:grid-cols-3 @3xl:grid-cols-2">
          {tiles.map((tile) => (
            <div
              key={tile.id}
              role="button"
              tabIndex={0}
              onClick={() => setFocus(tile.focus)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setFocus(tile.focus);
                }
              }}
              aria-pressed={focus === tile.focus}
              className={cn(
                "relative flex min-w-0 cursor-pointer items-center gap-3 rounded-lg border bg-card p-2.5 pr-6 text-left shadow-xs transition-colors hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                focus === tile.focus &&
                  "border-brand-accent ring-1 ring-brand-accent/40",
              )}
            >
              <TileInfo id={tile.id} stats={s} />
              <RingGauge
                value={tile.ring}
                max={tile.max}
                color={
                  tile.color ?? loadColor((tile.ring / (tile.max ?? 100)) * 100)
                }
                display={tile.display}
                size={60}
                thickness={5}
              />
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="truncate text-xs font-semibold text-foreground">
                  {tile.label}
                  {!running && (
                    <span className="font-normal text-muted-foreground">
                      {" "}
                      · avg
                    </span>
                  )}
                </span>
                <span className="truncate text-xs tabular-nums text-foreground">
                  {tile.primary}
                </span>
                <span className="flex min-w-0 items-center gap-1.5">
                  {tile.load !== undefined && (
                    <StatusPill percent={tile.load} />
                  )}
                  <span className="truncate text-[0.6875rem] tabular-nums text-muted-foreground">
                    {tile.range}
                  </span>
                </span>
              </span>
            </div>
          ))}
        </div>
      </div>

      <section className="rounded-lg border bg-card p-3 shadow-xs">
        <header className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="inline-flex h-8 flex-wrap items-center rounded-md bg-muted p-[0.1875rem]">
            {FOCUS.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setFocus(f.id)}
                className={cn(
                  "h-full rounded-sm px-3 text-xs font-medium transition-colors",
                  focus === f.id
                    ? "bg-background text-foreground shadow-sm"
                    : "text-foreground/60 hover:text-foreground",
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            {(focus === "gpu" || focus === "overview") && (
              <GpuToggle gpu={gpu} onChange={setGpu} />
            )}
            <ChartInfo id={focused.charts[0]} />
          </div>
        </header>
        <ChartById
          id={focused.charts[0]}
          history={history}
          gpu={gpu}
          isSummary={!running}
          hideTitle
          className="!bg-transparent !shadow-none !p-0"
        />
        {focused.charts.length > 1 && (
          <div className="mt-3 grid grid-cols-1 gap-3 border-t pt-3 @2xl:grid-cols-2">
            {focused.charts.slice(1).map((id) => (
              <ChartById
                key={id}
                id={id}
                history={history}
                gpu={gpu}
                isSummary={!running}
                compact
                help={CHART_HELP[id]}
                className="!shadow-none border"
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
};
