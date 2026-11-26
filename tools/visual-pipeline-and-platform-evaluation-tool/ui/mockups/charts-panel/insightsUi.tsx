// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { AlertTriangle, ChevronRight, Info, OctagonAlert } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { ChartById } from "./charts";
import {
  DEVICE_CHARTS,
  DEVICE_LABELS,
  type DeviceId,
  type Insight,
} from "./devices";
import type { FakePoint } from "./fakeMetrics";

const SEVERITY_STYLE = {
  critical: {
    icon: OctagonAlert,
    color: "var(--color-destructive)",
  },
  warning: {
    icon: AlertTriangle,
    color: "var(--color-yellow-chart)",
  },
  info: {
    icon: Info,
    color: "var(--color-brand-accent)",
  },
} as const;

export const SeverityIcon = ({
  severity,
  className,
}: {
  severity: Insight["severity"];
  className?: string;
}) => {
  const { icon: Icon, color } = SEVERITY_STYLE[severity];
  return (
    <Icon className={cn("size-4 shrink-0", className)} style={{ color }} />
  );
};

/** Same color-mix recipe as the shared status-* utilities. */
const tint = (color: string, percent: number) =>
  `color-mix(in oklch, ${color} ${percent}%, var(--background))`;

export const InsightList = ({
  insights,
  onSelect,
  limit,
}: {
  insights: Insight[];
  onSelect: (device: DeviceId) => void;
  limit?: number;
}) => (
  <ul className="flex flex-col divide-y">
    {insights.slice(0, limit).map((insight) => (
      <li key={insight.id}>
        <button
          type="button"
          onClick={() => onSelect(insight.device)}
          className="flex w-full items-start gap-2 py-2 text-left transition-colors hover:bg-accent/40"
        >
          <SeverityIcon severity={insight.severity} className="mt-0.5" />
          <span className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span className="text-xs font-medium text-foreground">
              {insight.title}
            </span>
            <span className="text-[0.6875rem] italic text-muted-foreground">
              {insight.hint}
            </span>
          </span>
          <ChevronRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        </button>
      </li>
    ))}
  </ul>
);

export const InsightCounts = ({ insights }: { insights: Insight[] }) => (
  <div className="flex items-center gap-1.5">
    {(["critical", "warning", "info"] as const).map((severity) => {
      const count = insights.filter((i) => i.severity === severity).length;
      if (count === 0) return null;
      const { color } = SEVERITY_STYLE[severity];
      return (
        <span
          key={severity}
          className="flex items-center gap-1 border px-1.5 py-0.5 text-[0.6875rem] font-semibold tabular-nums"
          style={{
            backgroundColor: tint(color, 12),
            borderColor: tint(color, 32),
            color: `color-mix(in oklch, ${color} 72%, var(--foreground))`,
          }}
        >
          <SeverityIcon severity={severity} className="size-3" />
          {count}
        </span>
      );
    })}
  </div>
);

export const DeviceDialog = ({
  device,
  onClose,
  history,
  gpu,
  running,
}: {
  device: DeviceId | null;
  onClose: () => void;
  history: FakePoint[];
  gpu: number;
  running: boolean;
}) => (
  <Dialog open={device !== null} onOpenChange={(open) => !open && onClose()}>
    <DialogContent className="sm:max-w-4xl max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>
          {device === "gpu"
            ? `GPU ${gpu}`
            : device
              ? DEVICE_LABELS[device]
              : ""}
        </DialogTitle>
        <DialogDescription>
          {running ? "Live" : "Run summary"} · last {history.length} s
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-4">
        {device &&
          DEVICE_CHARTS[device].map((id) => (
            <ChartById
              key={id}
              id={id}
              history={history}
              gpu={gpu}
              isSummary={!running}
              className="!shadow-none border"
            />
          ))}
      </div>
    </DialogContent>
  </Dialog>
);
