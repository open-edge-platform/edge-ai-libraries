// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useState, type ReactNode } from "react";
import { Cpu, Gauge, Gpu, Maximize2, MemoryStick } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CHART_LABELS, type ChartId } from "./chartCatalog";
import { ChartById } from "./charts";
import { average, gpuMaxEngine, type FakePoint } from "./fakeMetrics";
import { FakeVideo, GpuToggle, RunStatusBadge, Sparkline } from "./shared";
import type { PanelProps } from "./types";

const SECTIONS = ["pipeline", "cpu", "memory", "gpu", "npu"] as const;
const DEFAULT_OPEN = ["pipeline", "cpu", "gpu"];

const Stat = ({ value, unit }: { value: string; unit: string }) => (
  <span className="tabular-nums">
    <span className="font-semibold text-foreground">{value}</span>
    <span className="ml-0.5 text-muted-foreground">{unit}</span>
  </span>
);

const SectionHeader = ({
  icon,
  title,
  stats,
}: {
  icon: ReactNode;
  title: string;
  stats: ReactNode;
}) => (
  <div className="flex flex-1 items-center justify-between gap-3 pr-2">
    <span className="flex items-center gap-2 text-sm font-semibold">
      {icon}
      {title}
    </span>
    <span className="flex items-center gap-3 text-xs font-normal text-muted-foreground no-underline">
      {stats}
    </span>
  </div>
);

/** Option B: collapsible device sections with compact small multiples. */
export const OptionBPanel = ({
  history,
  elapsed,
  running,
  gpu,
  setGpu,
}: PanelProps) => {
  const [open, setOpen] = useState<string[]>(DEFAULT_OPEN);
  const [expanded, setExpanded] = useState<ChartId | null>(null);
  const isSummary = !running;
  const gpuKey = String(gpu);
  const val = (fn: (p: FakePoint) => number, decimals = 1) => {
    const values = history.map(fn);
    return (running ? (values.at(-1) ?? 0) : average(values)).toFixed(decimals);
  };

  const chart = (id: ChartId, compact = false) => (
    <div className="group relative min-w-0">
      <ChartById
        id={id}
        history={history}
        gpu={gpu}
        isSummary={isSummary}
        compact={compact}
      />
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={`Expand ${CHART_LABELS[id]}`}
        onClick={() => setExpanded(id)}
        className="absolute right-2 top-2 opacity-60 group-hover:opacity-100"
      >
        <Maximize2 className="size-4" />
      </Button>
    </div>
  );

  return (
    <div className="flex flex-col w-full h-full bg-background p-4 space-y-4 overflow-y-auto overflow-x-hidden min-w-0">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Test pipeline</h2>
        <div className="flex items-center gap-2">
          <RunStatusBadge running={running} elapsed={elapsed} />
          <Button
            variant="outline"
            size="sm"
            onClick={() => setOpen(open.length > 0 ? [] : [...SECTIONS])}
          >
            {open.length > 0 ? "Collapse all" : "Expand all"}
          </Button>
        </div>
      </div>

      <Tabs value="media" className="flex flex-col min-w-0">
        <TabsList className="grid w-full grid-flow-col auto-cols-fr">
          <TabsTrigger value="media">
            {running ? "Live Preview" : "Output Video"}
          </TabsTrigger>
          <TabsTrigger value="metadata">Metadata JSON</TabsTrigger>
        </TabsList>
        <FakeVideo tick={elapsed} live={running} className="mt-2" />
      </Tabs>

      <Accordion
        type="multiple"
        value={open}
        onValueChange={setOpen}
        className="border shadow-md"
      >
        <AccordionItem value="pipeline" className="px-3">
          <AccordionTrigger className="hover:no-underline">
            <SectionHeader
              icon={<Gauge className="size-4 text-magenta-chart" />}
              title="Pipeline"
              stats={
                <>
                  <Stat value={val((p) => p.fps)} unit="fps" />
                  <Stat value={val((p) => p.latencyAvg)} unit="ms" />
                </>
              }
            />
          </AccordionTrigger>
          <AccordionContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {chart("fps")}
            {chart("latency")}
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="cpu" className="px-3">
          <AccordionTrigger className="hover:no-underline">
            <SectionHeader
              icon={<Cpu className="size-4 text-green-chart" />}
              title="CPU"
              stats={
                <>
                  <Stat value={val((p) => p.cpu)} unit="%" />
                  <Stat value={val((p) => p.cpuFreq, 2)} unit="GHz" />
                  <Stat value={val((p) => p.cpuTemp)} unit="°C" />
                </>
              }
            />
          </AccordionTrigger>
          <AccordionContent className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {chart("cpuUsage", true)}
            {chart("cpuFreq", true)}
            {chart("cpuTemp", true)}
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="memory" className="px-3">
          <AccordionTrigger className="hover:no-underline">
            <SectionHeader
              icon={<MemoryStick className="size-4 text-magenta-chart" />}
              title="Memory"
              stats={
                <>
                  <Sparkline
                    values={history.map((p) => p.memory)}
                    color="var(--color-magenta-chart)"
                    className="h-5 w-24"
                  />
                  <Stat value={val((p) => p.memory)} unit="%" />
                </>
              }
            />
          </AccordionTrigger>
          <AccordionContent>{chart("memory")}</AccordionContent>
        </AccordionItem>

        <AccordionItem value="gpu" className="px-3">
          <div className="flex items-center gap-2">
            <div className="flex-1">
              <AccordionTrigger className="hover:no-underline">
                <SectionHeader
                  icon={<Gpu className="size-4 text-yellow-chart" />}
                  title={`GPU ${gpu}`}
                  stats={
                    <>
                      <Stat
                        value={val((p) => gpuMaxEngine(p.gpus[gpuKey]))}
                        unit="%"
                      />
                      <Stat
                        value={val((p) => p.gpus[gpuKey]?.frequency ?? 0, 2)}
                        unit="GHz"
                      />
                      <Stat
                        value={val((p) => p.gpus[gpuKey]?.gpuPower ?? 0)}
                        unit="W"
                      />
                    </>
                  }
                />
              </AccordionTrigger>
            </div>
            <GpuToggle gpu={gpu} onChange={setGpu} />
          </div>
          <AccordionContent className="space-y-4">
            {chart("gpuEngines")}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {chart("gpuFreq", true)}
              {chart("gpuPower", true)}
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="npu" className="px-3">
          <AccordionTrigger className="hover:no-underline">
            <SectionHeader
              icon={<Gpu className="size-4 text-geode-chart" />}
              title="NPU"
              stats={
                <>
                  <Stat value={val((p) => p.npu)} unit="%" />
                  <Stat value={val((p) => p.npuPower)} unit="W" />
                  <Stat value={val((p) => p.npuFreq / 1000, 2)} unit="GHz" />
                </>
              }
            />
          </AccordionTrigger>
          <AccordionContent className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {chart("npuUsage", true)}
            {chart("npuPower", true)}
            {chart("npuFreq", true)}
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      <Dialog
        open={expanded !== null}
        onOpenChange={(isOpen) => !isOpen && setExpanded(null)}
      >
        <DialogContent className="sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>{expanded ? CHART_LABELS[expanded] : ""}</DialogTitle>
            <DialogDescription>
              {running ? "Live" : "Run summary"} · last {history.length} s
            </DialogDescription>
          </DialogHeader>
          {expanded && (
            <ChartById
              id={expanded}
              history={history}
              gpu={gpu}
              isSummary={isSummary}
              hideTitle
              className="!shadow-none !p-0"
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};
