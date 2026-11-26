// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import {
  Cpu,
  Gauge,
  Gpu,
  Lightbulb,
  MemoryStick,
  Thermometer,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  buildInsights,
  deviceStats,
  loadColor,
  loadLabel,
  type DeviceId,
} from "./devices";
import { CardShell, MeterBars, RingGauge, StatRow } from "./gauges";
import { DeviceDialog, InsightCounts, InsightList } from "./insightsUi";
import { FakeVideo, GpuToggle, RunStatusBadge, Sparkline } from "./shared";
import type { PanelProps } from "./types";

const pct = (v: number) => `${v.toFixed(1)}%`;

/** Option D: device cards with ring gauges, stat lists and an Insights card. */
export const OptionDPanel = ({
  history,
  elapsed,
  running,
  gpu,
  setGpu,
}: PanelProps) => {
  const [openDevice, setOpenDevice] = useState<DeviceId | null>(null);
  const s = deviceStats(history, gpu, running);
  const insights = buildInsights(history, gpu, running);

  return (
    <div className="@container flex flex-col w-full h-full bg-background p-4 space-y-4 overflow-y-auto overflow-x-hidden min-w-0">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Test pipeline</h2>
        <RunStatusBadge running={running} elapsed={elapsed} />
      </div>

      <div className="grid grid-cols-1 gap-3 @2xl:grid-cols-2 @5xl:grid-cols-3">
        <CardShell
          icon={<Lightbulb className="size-4 text-yellow-chart" />}
          title="Insights"
          action={<InsightCounts insights={insights} />}
          className="@2xl:row-span-2"
        >
          <InsightList insights={insights} onSelect={setOpenDevice} />
        </CardShell>

        <div className="flex min-w-0 flex-col overflow-hidden rounded-lg border shadow-xs @2xl:row-span-2">
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
          <FakeVideo tick={elapsed} live={running} className="flex-1" />
        </div>

        <CardShell
          icon={<Gauge className="size-4 text-magenta-chart" />}
          title="Pipeline"
          onOpen={() => setOpenDevice("pipeline")}
        >
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-[0.625rem] font-semibold uppercase tracking-widest text-muted-foreground">
                Frame rate{!running && " · avg"}
              </p>
              <p className="text-2xl font-bold tabular-nums">
                {s.fps.value.toFixed(1)}
                <span className="ml-1 text-xs text-muted-foreground">fps</span>
              </p>
            </div>
            <div>
              <p className="text-[0.625rem] font-semibold uppercase tracking-widest text-muted-foreground">
                Latency{!running && " · avg"}
              </p>
              <p className="text-2xl font-bold tabular-nums">
                {s.latency.value.toFixed(1)}
                <span className="ml-1 text-xs text-muted-foreground">ms</span>
              </p>
            </div>
          </div>
          <div className="grid gap-1">
            <StatRow
              label="FPS min / max"
              value={`${s.fps.min.toFixed(1)} / ${s.fps.max.toFixed(1)}`}
            />
            <StatRow
              label="Latency min / max"
              value={`${s.latencyMin.min.toFixed(0)} / ${s.latencyMax.max.toFixed(0)} ms`}
            />
          </div>
          <Sparkline
            values={s.fps.series}
            color="var(--color-magenta-chart)"
            className="h-12"
          />
        </CardShell>

        <CardShell
          icon={<Cpu className="size-4 text-green-chart" />}
          title="CPU"
          onOpen={() => setOpenDevice("cpu")}
        >
          <div className="flex items-center gap-4">
            <RingGauge
              value={s.cpu.value}
              color={loadColor(s.cpu.value)}
              display={pct(s.cpu.value)}
              caption="CPU"
            />
            <div className="grid flex-1 gap-1">
              <StatRow label="Usage" value={pct(s.cpu.value)} />
              <StatRow
                label="Frequency"
                value={`${s.cpuFreq.value.toFixed(2)} GHz`}
              />
              <StatRow
                label="Temperature"
                value={`${s.cpuTemp.value.toFixed(0)} °C`}
              />
              <StatRow
                label="Status"
                value={
                  <span style={{ color: loadColor(s.cpu.value) }}>
                    {loadLabel(s.cpu.value)}
                  </span>
                }
              />
            </div>
          </div>
          <Sparkline
            values={s.cpu.series}
            color="var(--color-green-chart)"
            className="h-12"
          />
        </CardShell>

        <CardShell
          icon={<Gpu className="size-4 text-yellow-chart" />}
          title={`GPU ${gpu}`}
          action={<GpuToggle gpu={gpu} onChange={setGpu} />}
          onOpen={() => setOpenDevice("gpu")}
        >
          <div className="flex items-center gap-4">
            <RingGauge
              value={s.gpu.value}
              color={loadColor(s.gpu.value)}
              display={pct(s.gpu.value)}
              caption="peak engine"
            />
            <div className="grid flex-1 gap-1">
              <StatRow
                label="Frequency"
                value={`${s.gpuFreq.value.toFixed(2)} GHz`}
              />
              <StatRow
                label="GPU power"
                value={`${s.gpuPower.value.toFixed(1)} W`}
              />
              <StatRow
                label="Package power"
                value={`${s.pkgPower.value.toFixed(1)} W`}
              />
            </div>
          </div>
          <MeterBars items={s.engines} />
          <Sparkline
            values={s.gpu.series}
            color="var(--color-yellow-chart)"
            className="h-10"
          />
        </CardShell>

        <CardShell
          icon={<Gpu className="size-4 text-geode-chart" />}
          title="NPU"
          onOpen={() => setOpenDevice("npu")}
        >
          <div className="flex items-center gap-4">
            <RingGauge
              value={s.npu.value}
              color={loadColor(s.npu.value)}
              display={pct(s.npu.value)}
              caption="NPU"
            />
            <div className="grid flex-1 gap-1">
              <StatRow label="Usage" value={pct(s.npu.value)} />
              <StatRow
                label="Power"
                value={`${s.npuPower.value.toFixed(1)} W`}
              />
              <StatRow
                label="Frequency"
                value={`${(s.npuFreq.value / 1000).toFixed(2)} GHz`}
              />
            </div>
          </div>
          <Sparkline
            values={s.npu.series}
            color="var(--color-geode-chart)"
            className="h-12"
          />
        </CardShell>

        <CardShell
          icon={<MemoryStick className="size-4 text-magenta-chart" />}
          title="Memory"
          onOpen={() => setOpenDevice("memory")}
        >
          <div className="flex items-center gap-4">
            <RingGauge
              value={s.memory.value}
              color={loadColor(s.memory.value)}
              display={pct(s.memory.value)}
              caption="RAM"
            />
            <div className="grid flex-1 gap-1">
              <StatRow label="Utilization" value={pct(s.memory.value)} />
              <StatRow label="Min" value={pct(s.memory.min)} />
              <StatRow label="Max" value={pct(s.memory.max)} />
            </div>
          </div>
          <Sparkline
            values={s.memory.series}
            color="var(--color-magenta-chart)"
            className="h-12"
          />
        </CardShell>

        <CardShell
          icon={<Thermometer className="size-4 text-orange-chart" />}
          title="Thermal & Power"
          onOpen={() => setOpenDevice("thermal")}
        >
          <div className="flex items-center gap-4">
            <RingGauge
              value={s.cpuTemp.value}
              color={loadColor(s.cpuTemp.value)}
              display={`${s.cpuTemp.value.toFixed(0)}°C`}
              caption="CPU"
            />
            <div className="grid flex-1 gap-1">
              <StatRow
                label="CPU max"
                value={`${s.cpuTemp.max.toFixed(0)} °C`}
              />
              <StatRow
                label={`GPU ${gpu} + package`}
                value={`${s.pkgPower.value.toFixed(1)} W`}
              />
              <StatRow label="NPU" value={`${s.npuPower.value.toFixed(1)} W`} />
              <StatRow
                label="Total"
                value={`${s.totalPower.value.toFixed(1)} W`}
              />
            </div>
          </div>
          <Sparkline
            values={s.cpuTemp.series}
            color="var(--color-orange-chart)"
            className="h-12"
          />
        </CardShell>
      </div>

      <DeviceDialog
        device={openDevice}
        onClose={() => setOpenDevice(null)}
        history={history}
        gpu={gpu}
        running={running}
      />
    </div>
  );
};
