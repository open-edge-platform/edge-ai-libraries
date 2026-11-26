// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import type { ChartId } from "./chartCatalog";
import { ChartById } from "./charts";
import { buildKpis, type DeviceTab } from "./kpis";
import { FakeVideo, GpuToggle, KpiTile, RunStatusBadge } from "./shared";
import type { PanelProps } from "./types";

/** Option A: sticky KPI strip + device tabs. */
export const OptionAPanel = ({
  history,
  elapsed,
  running,
  gpu,
  setGpu,
}: PanelProps) => {
  const [tab, setTab] = useState<DeviceTab>("overview");
  const [videoOpen, setVideoOpen] = useState(true);
  const isSummary = !running;
  const kpis = buildKpis(history, running, gpu);
  const chart = (id: ChartId) => (
    <ChartById id={id} history={history} gpu={gpu} isSummary={isSummary} />
  );

  return (
    <div className="@container flex flex-col w-full h-full bg-background p-4 space-y-4 overflow-y-auto overflow-x-hidden min-w-0">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Test pipeline</h2>
        <RunStatusBadge running={running} elapsed={elapsed} />
      </div>

      <div className="border shadow-md">
        <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
          <Tabs defaultValue="preview">
            <TabsList variant="line" className="h-8">
              <TabsTrigger value="preview">
                {running ? "Live Preview" : "Output Video"}
              </TabsTrigger>
              <TabsTrigger value="metadata">Metadata JSON</TabsTrigger>
            </TabsList>
          </Tabs>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={videoOpen ? "Collapse preview" : "Expand preview"}
            onClick={() => setVideoOpen((open) => !open)}
          >
            {videoOpen ? <ChevronUp /> : <ChevronDown />}
          </Button>
        </div>
        {videoOpen && <FakeVideo tick={elapsed} live={running} />}
      </div>

      <div className="sticky -top-4 z-10 -mx-4 border-b bg-background/95 px-4 py-3 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="grid grid-cols-3 gap-2 @4xl:grid-cols-6">
          {kpis.map((kpi) => (
            <KpiTile
              key={kpi.id}
              {...kpi}
              summary={isSummary}
              active={tab === kpi.tab}
              onClick={() => setTab(kpi.tab)}
            />
          ))}
        </div>
      </div>

      <Tabs
        value={tab}
        onValueChange={(value) => setTab(value as DeviceTab)}
        className="min-w-0"
      >
        <TabsList className="grid w-full grid-flow-col auto-cols-fr">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
          <TabsTrigger value="cpu">CPU &amp; Memory</TabsTrigger>
          <TabsTrigger value="gpu">GPU</TabsTrigger>
          <TabsTrigger value="npu">NPU</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-2 space-y-4">
          {chart("fps")}
          {chart("utilization")}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {chart("cpuTemp")}
            {chart("power")}
          </div>
        </TabsContent>

        <TabsContent value="pipeline" className="mt-2 space-y-4">
          {chart("fps")}
          {chart("latency")}
        </TabsContent>

        <TabsContent value="cpu" className="mt-2">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {chart("cpuUsage")}
            {chart("cpuFreq")}
            {chart("cpuTemp")}
            {chart("memory")}
          </div>
        </TabsContent>

        <TabsContent value="gpu" className="mt-2 space-y-4">
          <div
            className={cn(
              "flex items-center justify-between gap-2 border bg-muted/30 px-3 py-2",
            )}
          >
            <span className="text-sm font-medium">Device</span>
            <GpuToggle gpu={gpu} onChange={setGpu} />
          </div>
          {chart("gpuEngines")}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {chart("gpuFreq")}
            {chart("gpuPower")}
          </div>
        </TabsContent>

        <TabsContent value="npu" className="mt-2 space-y-4">
          {chart("npuUsage")}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {chart("npuPower")}
            {chart("npuFreq")}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};
