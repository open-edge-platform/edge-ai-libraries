// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Badge } from "@/components/ui/badge";
import type { PipelineEvent } from "@/api/api.generated";

const SOURCE_LABELS: Record<string, string> = {
  "proximity-trigger": "Trigger",
  vlm: "VLM",
};

const formatPosition = (event: PipelineEvent): string => {
  if (event.pts_seconds != null) {
    const total = Math.max(0, event.pts_seconds);
    const minutes = Math.floor(total / 60);
    const seconds = (total % 60).toFixed(1).padStart(4, "0");
    return `${minutes}:${seconds}`;
  }
  return new Date(event.timestamp_ms).toLocaleTimeString();
};

type LivePipelineEventsProps = {
  events: PipelineEvent[];
  isRunning: boolean;
};

export const LivePipelineEvents = ({
  events,
  isRunning,
}: LivePipelineEventsProps) => {
  const newestFirst = [...events].reverse();
  const triggeredCount = events.filter(
    (event) => event.source === "proximity-trigger",
  ).length;

  return (
    <div className="border bg-muted/30">
      <div className="flex items-center justify-between px-3 py-2 border-b">
        <span className="text-sm font-medium">Live events</span>
        <span className="text-xs text-muted-foreground">
          Triggered events: {triggeredCount}
        </span>
      </div>
      {newestFirst.length === 0 ? (
        <p className="px-3 py-2 text-sm text-muted-foreground">
          Waiting for events...
        </p>
      ) : (
        <ul className="max-h-56 overflow-y-auto divide-y">
          {newestFirst.map((event, index) => (
            <li
              key={`${event.timestamp_ms}-${event.source}-${events.length - index}`}
              className={`flex items-start gap-2 px-3 py-2 text-sm ${
                index === 0 && isRunning ? "bg-primary/10" : ""
              }`}
            >
              <span className="font-mono text-xs text-muted-foreground pt-0.5 shrink-0">
                {formatPosition(event)}
              </span>
              <Badge
                variant={event.source === "vlm" ? "default" : "secondary"}
                className="shrink-0"
              >
                {SOURCE_LABELS[event.source] ?? event.source}
              </Badge>
              <span className="whitespace-pre-wrap break-words min-w-0">
                {event.prompt && (
                  <span className="text-muted-foreground">
                    {event.prompt} →{" "}
                  </span>
                )}
                <span className={event.prompt ? "font-medium" : undefined}>
                  {event.text}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
