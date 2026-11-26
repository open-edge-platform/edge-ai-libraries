// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Columns2,
  MoreHorizontal,
  PinOff,
  Plus,
  RotateCcw,
  Rows2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { CHART_GROUPS, CHART_LABELS, type ChartId } from "./chartCatalog";
import { ChartById } from "./charts";
import { buildKpis } from "./kpis";
import { FakeVideo, GpuToggle, KpiTile, RunStatusBadge } from "./shared";
import type { PanelProps } from "./types";

const PRESETS: Record<string, ChartId[]> = {
  Default: ["fps", "gpuEngines", "cpuUsage", "latency"],
  "GPU focus": ["gpuEngines", "gpuFreq", "gpuPower", "fps"],
  "CPU focus": ["cpuUsage", "cpuFreq", "cpuTemp", "memory"],
  Overview: ["fps", "utilization", "power", "latency"],
};

const GPU_CHARTS: ChartId[] = [
  "gpuEngines",
  "gpuFreq",
  "gpuPower",
  "utilization",
  "power",
];

/** Option C: video + KPIs side by side, user-pinned charts. */
export const OptionCPanel = ({
  history,
  elapsed,
  running,
  gpu,
  setGpu,
}: PanelProps) => {
  const [preset, setPreset] = useState("Default");
  const [pinned, setPinned] = useState<ChartId[]>(PRESETS.Default);
  const [columns, setColumns] = useState<1 | 2>(2);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [draft, setDraft] = useState<ChartId[]>([]);
  const isSummary = !running;
  const kpis = buildKpis(history, running, gpu);

  const applyPreset = (name: string) => {
    setPreset(name);
    setPinned(PRESETS[name]);
  };

  const move = (id: ChartId, delta: number) =>
    setPinned((list) => {
      const from = list.indexOf(id);
      const to = from + delta;
      if (to < 0 || to >= list.length) return list;
      const next = [...list];
      [next[from], next[to]] = [next[to], next[from]];
      return next;
    });

  const openPicker = () => {
    setDraft(pinned);
    setPickerOpen(true);
  };

  return (
    <div className="flex flex-col w-full h-full bg-background p-4 space-y-4 overflow-y-auto overflow-x-hidden min-w-0">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Test pipeline</h2>
        <RunStatusBadge running={running} elapsed={elapsed} />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="min-w-0 border shadow-md">
          <div className="border-b px-3 py-1.5">
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
        <div className="grid grid-cols-2 content-start gap-2">
          {kpis.map((kpi) => (
            <KpiTile
              key={kpi.id}
              {...kpi}
              values={undefined}
              summary={isSummary}
            />
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-y py-2">
        <Button size="sm" onClick={openPicker}>
          <Plus /> Add chart
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="outline">
              Preset: {preset}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuLabel>Chart presets</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuRadioGroup value={preset} onValueChange={applyPreset}>
              {Object.keys(PRESETS).map((name) => (
                <DropdownMenuRadioItem key={name} value={name}>
                  {name}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        <div className="inline-flex h-8 items-center bg-muted p-[0.1875rem]">
          {([1, 2] as const).map((count) => (
            <button
              key={count}
              type="button"
              aria-label={`${count} column${count > 1 ? "s" : ""}`}
              onClick={() => setColumns(count)}
              className={cn(
                "flex h-full items-center px-2 transition-colors",
                columns === count
                  ? "bg-background text-foreground shadow-sm"
                  : "text-foreground/60 hover:text-foreground",
              )}
            >
              {count === 1 ? (
                <Rows2 className="size-4" />
              ) : (
                <Columns2 className="size-4" />
              )}
            </button>
          ))}
        </div>
        <Button size="sm" variant="ghost" onClick={() => applyPreset(preset)}>
          <RotateCcw /> Reset
        </Button>
        {pinned.some((id) => GPU_CHARTS.includes(id)) && (
          <div className="ml-auto">
            <GpuToggle gpu={gpu} onChange={setGpu} />
          </div>
        )}
      </div>

      <div
        className={cn(
          "grid grid-cols-1 gap-4",
          columns === 2 && "sm:grid-cols-2",
        )}
      >
        {pinned.map((id, index) => (
          <div key={id} className="group relative min-w-0">
            <ChartById
              id={id}
              history={history}
              gpu={gpu}
              isSummary={isSummary}
            />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`${CHART_LABELS[id]} options`}
                  className="absolute right-2 top-2 opacity-60 group-hover:opacity-100"
                >
                  <MoreHorizontal className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  disabled={index === 0}
                  onClick={() => move(id, -1)}
                >
                  <ArrowUp /> Move up
                </DropdownMenuItem>
                <DropdownMenuItem
                  disabled={index === pinned.length - 1}
                  onClick={() => move(id, 1)}
                >
                  <ArrowDown /> Move down
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  variant="destructive"
                  onClick={() =>
                    setPinned((list) => list.filter((item) => item !== id))
                  }
                >
                  <PinOff /> Unpin
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ))}
        <button
          type="button"
          onClick={openPicker}
          className={cn(
            "flex min-h-24 items-center justify-center gap-2 border-2 border-dashed text-sm text-muted-foreground transition-colors hover:border-brand-accent hover:text-brand-accent",
            columns === 2 && pinned.length % 2 === 0 && "sm:col-span-2",
          )}
        >
          <Plus className="size-4" /> Add chart
        </button>
      </div>

      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add charts</DialogTitle>
            <DialogDescription>
              Choose which metrics are pinned to the panel. Your selection is
              remembered for this browser.
            </DialogDescription>
          </DialogHeader>
          <div className="grid max-h-[24rem] gap-4 overflow-y-auto">
            {CHART_GROUPS.map((group) => (
              <div key={group.group} className="space-y-2">
                <p className="text-[0.625rem] font-semibold uppercase tracking-widest text-muted-foreground">
                  {group.group}
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {group.items.map((item) => {
                    const checked = draft.includes(item.id);
                    return (
                      <Label
                        key={item.id}
                        className="flex cursor-pointer items-center gap-2 border px-3 py-2 font-normal hover:bg-accent/40"
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={(value) =>
                            setDraft((list) =>
                              value
                                ? [...list, item.id]
                                : list.filter((id) => id !== item.id),
                            )
                          }
                        />
                        {item.label}
                      </Label>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPickerOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                setPinned(draft);
                setPickerOpen(false);
              }}
            >
              Apply ({draft.length})
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
