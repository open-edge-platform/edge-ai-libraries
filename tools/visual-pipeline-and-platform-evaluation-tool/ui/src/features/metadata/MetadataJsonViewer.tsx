import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsRight,
  MoreHorizontal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { highlightJson } from "@/lib/jsonUtils";

const PRIMARY_GENAI_METRIC_KEYS = [
  "num_input_tokens",
  "num_generated_tokens",
  "ttft_mean",
  "ttft_std",
  "tpot_mean",
  "tpot_std",
  "generate_duration_mean",
  "generate_duration_std",
  "throughput_mean",
  "throughput_std",
] as const;

const collapseGenAIMetrics = (
  raw: string,
): { record?: Record<string, unknown>; canExpand: boolean } => {
  try {
    const record = JSON.parse(raw) as Record<string, unknown>;
    const metrics = record.metrics;
    if (!metrics || typeof metrics !== "object" || Array.isArray(metrics)) {
      return { canExpand: false };
    }

    const metricRecord = metrics as Record<string, unknown>;
    const collapsedMetrics: Record<string, unknown> = {};

    PRIMARY_GENAI_METRIC_KEYS.forEach((key) => {
      if (key in metricRecord) {
        collapsedMetrics[key] = metricRecord[key];
      }
    });

    const hiddenCount = Object.keys(metricRecord).filter(
      (key) => !(PRIMARY_GENAI_METRIC_KEYS as readonly string[]).includes(key),
    ).length;

    if (hiddenCount === 0) {
      return { record, canExpand: false };
    }

    return {
      record: { ...record, metrics: collapsedMetrics },
      canExpand: true,
    };
  } catch {
    return { canExpand: false };
  }
};

const formatJsonValue = (value: unknown): string =>
  JSON.stringify(value, null, 2).replace(/\n/g, "\n  ");

const HighlightedJsonFragment = ({ children }: { children: string }) => (
  <span dangerouslySetInnerHTML={{ __html: highlightJson(children) }} />
);

const InlineMetadataJsonViewer = ({
  record,
  showAllMetrics,
  onToggleMetrics,
}: {
  record: Record<string, unknown>;
  showAllMetrics: boolean;
  onToggleMetrics: () => void;
}) => {
  const entries = Object.entries(record);

  return (
    <pre className="p-3 font-mono text-xs leading-5 whitespace-pre-wrap break-all bg-transparent">
      <code className="hljs">
        <HighlightedJsonFragment>{"{\n"}</HighlightedJsonFragment>
        {entries.map(([key, value], index) => {
          const comma = index < entries.length - 1 ? "," : "";

          if (key !== "metrics" || typeof value !== "object" || !value) {
            return (
              <HighlightedJsonFragment key={key}>
                {`  ${JSON.stringify(key)}: ${formatJsonValue(value)}${comma}\n`}
              </HighlightedJsonFragment>
            );
          }

          const metrics = Object.entries(value as Record<string, unknown>);

          return (
            <span key={key}>
              <HighlightedJsonFragment>{`  ${JSON.stringify(key)}: {\n`}</HighlightedJsonFragment>
              {metrics.map(([metricKey, metricValue], metricIndex) => {
                const metricComma = metricIndex < metrics.length - 1 ? "," : "";
                return (
                  <HighlightedJsonFragment key={metricKey}>
                    {`    ${JSON.stringify(metricKey)}: ${formatJsonValue(metricValue)}${metricComma}\n`}
                  </HighlightedJsonFragment>
                );
              })}
              <span className="inline-flex pl-8">
                <Button
                  variant="ghost"
                  size="icon-xs"
                  onClick={onToggleMetrics}
                  className="h-4 w-5 rounded-sm p-0 text-muted-foreground hover:text-foreground"
                  aria-label={
                    showAllMetrics ? "Collapse metrics" : "Expand metrics"
                  }
                  title={showAllMetrics ? "Collapse metrics" : "Expand metrics"}
                >
                  <MoreHorizontal className="h-3 w-3" />
                </Button>
              </span>
              <HighlightedJsonFragment>{"\n"}</HighlightedJsonFragment>
              <HighlightedJsonFragment>{`  }${comma}\n`}</HighlightedJsonFragment>
            </span>
          );
        })}
        <HighlightedJsonFragment>{"}"}</HighlightedJsonFragment>
      </code>
    </pre>
  );
};

export const MetadataJsonViewer = ({
  lines,
  stale = false,
}: {
  lines: string[];
  stale?: boolean;
}) => {
  const [currentIndex, setCurrentIndex] = useState(lines.length - 1);
  const [followLatest, setFollowLatest] = useState(true);
  const [showAllMetrics, setShowAllMetrics] = useState(false);

  useEffect(() => {
    if (followLatest && lines.length > 0) {
      setCurrentIndex(lines.length - 1);
    }
  }, [lines.length, followLatest]);

  const goPrev = useCallback(() => {
    setFollowLatest(false);
    setCurrentIndex((index) => Math.max(0, index - 1));
  }, []);

  const goNext = useCallback(() => {
    setCurrentIndex((index) => {
      const next = Math.min(lines.length - 1, index + 1);
      if (next === lines.length - 1) setFollowLatest(true);
      return next;
    });
  }, [lines.length]);

  const goLatest = useCallback(() => {
    setFollowLatest(true);
    setCurrentIndex(lines.length - 1);
  }, [lines.length]);

  const safeIndex =
    lines.length > 0
      ? Math.max(0, Math.min(currentIndex, lines.length - 1))
      : 0;
  const currentLine = lines[safeIndex] ?? "";
  const collapsedLine = useMemo(
    () => collapseGenAIMetrics(currentLine),
    [currentLine],
  );
  const displayedRecord = showAllMetrics
    ? (() => {
        try {
          return JSON.parse(currentLine) as Record<string, unknown>;
        } catch {
          return undefined;
        }
      })()
    : collapsedLine.record;
  const highlightedHtml = useMemo(
    () => (currentLine ? highlightJson(currentLine) : ""),
    [currentLine],
  );
  const canToggleMetrics = collapsedLine.canExpand;

  if (lines.length === 0) {
    return (
      <div className="min-h-[100px] flex items-center justify-center border bg-muted/20 p-3">
        <p className="text-sm text-muted-foreground">
          Waiting for JSON entries...
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col space-y-2 min-w-0">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon-sm"
            onClick={goPrev}
            disabled={safeIndex === 0}
            aria-label="Previous entry"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon-sm"
            onClick={goNext}
            disabled={safeIndex >= lines.length - 1}
            aria-label="Next entry"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <span className="text-xs tabular-nums text-muted-foreground">
          {safeIndex + 1} / {lines.length}
        </span>
        <Button
          variant={followLatest ? "secondary" : "outline"}
          size="sm"
          onClick={goLatest}
          className="text-xs gap-1 h-7"
        >
          <ChevronsRight className="h-3.5 w-3.5" />
          Follow
        </Button>
      </div>
      <div
        className={`min-h-[100px] border bg-zinc-100 dark:bg-zinc-900/80 text-zinc-700 dark:text-zinc-300 ${showAllMetrics ? "overflow-visible" : "max-h-[40vh] overflow-auto"} ${stale ? "border-2 dark:border-energy-blue/40 dark:shadow-energy-blue/20 dark:ring-1 dark:ring-energy-blue/20 border-classic-blue/40 shadow-classic-blue/20 ring-1 ring-classic-blue/20 shadow-lg" : ""}`}
      >
        {canToggleMetrics && displayedRecord ? (
          <InlineMetadataJsonViewer
            record={displayedRecord}
            showAllMetrics={showAllMetrics}
            onToggleMetrics={() => setShowAllMetrics((expanded) => !expanded)}
          />
        ) : (
          <pre className="p-3 font-mono text-xs leading-5 whitespace-pre-wrap break-all bg-transparent">
            <code
              className="hljs"
              dangerouslySetInnerHTML={{ __html: highlightedHtml }}
            />
          </pre>
        )}
      </div>
    </div>
  );
};
