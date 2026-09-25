import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";

type LatencyMetricsProps = {
  latencyMaxMs: number;
  latencyMaxStddevMs?: number | null;
  latencyAvgMs?: number | null;
  latencyAvgStddevMs?: number | null;
  latencyMinMs?: number | null;
  latencyMinStddevMs?: number | null;
};

export const LatencyMetrics = ({
  latencyMaxMs,
  latencyMaxStddevMs,
  latencyAvgMs,
  latencyAvgStddevMs,
  latencyMinMs,
  latencyMinStddevMs,
}: LatencyMetricsProps) => {
  return (
    <HoverCard openDelay={100} closeDelay={100}>
      <HoverCardTrigger asChild>
        <span className="cursor-default underline decoration-dotted underline-offset-2">
          {`${latencyMaxMs.toFixed(1)} ms`}
        </span>
      </HoverCardTrigger>
      <HoverCardContent side="top" className="w-auto text-sm">
        <div className="grid grid-cols-[auto_auto_1fr] gap-x-3 gap-y-1">
          <span>Latency Max</span>
          <span className="font-bold text-right">
            {`${latencyMaxMs.toFixed(1)} ms`}
          </span>
          <span className="text-muted-foreground">
            (std dev:{" "}
            {typeof latencyMaxStddevMs === "number"
              ? `${latencyMaxStddevMs.toFixed(1)} ms`
              : "N/A"}
            )
          </span>
          <span>Latency Avg</span>
          <span className="text-right">
            {typeof latencyAvgMs === "number"
              ? `${latencyAvgMs.toFixed(1)} ms`
              : "-"}
          </span>
          <span className="text-muted-foreground">
            (std dev:{" "}
            {typeof latencyAvgStddevMs === "number"
              ? `${latencyAvgStddevMs.toFixed(1)} ms`
              : "N/A"}
            )
          </span>
          <span>Latency Min</span>
          <span className="text-right">
            {typeof latencyMinMs === "number"
              ? `${latencyMinMs.toFixed(1)} ms`
              : "-"}
          </span>
          <span className="text-muted-foreground">
            (std dev:{" "}
            {typeof latencyMinStddevMs === "number"
              ? `${latencyMinStddevMs.toFixed(1)} ms`
              : "N/A"}
            )
          </span>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
};
