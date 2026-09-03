import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MetricsDashboard } from "@/features/metrics/MetricsDashboard.tsx";
import {
  MetricChart,
  type MetricDataPoint,
} from "@/features/metrics/MetricChart.tsx";
import {
  CHART_MAX_DATA_POINTS,
  getRecentYAxisMax,
} from "@/features/metrics/charts";
import WebRTCVideoPlayer from "@/features/webrtc/WebRTCVideoPlayer.tsx";
import {
  useFrozenMetrics,
  type FrozenSnapshotOverrides,
} from "@/hooks/useFrozenMetrics";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useGetPerformanceStatusesQuery } from "@/api/api.generated";
import { Button } from "@/components/ui/button";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsRight,
  ExternalLink,
  MoreHorizontal,
} from "lucide-react";
import { highlightJson } from "@/lib/jsonUtils";
import "@/lib/hljs-theme.css";

const MAX_JSON_LINES_PER_PIPELINE = 400;
const METADATA_POLL_INTERVAL = 3000;
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

type ConnectionState = "connecting" | "open" | "error" | "closed";

interface GenAIMetricsPoint extends MetricDataPoint {
  ttft: number;
  tpot: number;
  totalLatency: number;
}

type PerformanceJobStatusWithMetadata = {
  metadata_stream_urls?: Record<string, string[]> | null;
};

/** Label shown in the pipeline tab: "job-short … pipeline-short" */
const buildStreamLabel = (jobId: string, pipelineId: string): string => {
  const shortJob = jobId.slice(0, 8);
  const shortPipeline = pipelineId.replace(/^__graph-/, "").slice(0, 8);
  return `${shortJob} / ${shortPipeline}`;
};

/** Shorten a stream URL to its last two meaningful path segments. */
const shortenStreamUrl = (url: string): string => {
  const segments = url.replace(/\/+$/, "").split("/").filter(Boolean);
  return segments.length > 2 ? `…/${segments.slice(-2).join("/")}` : url;
};

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

const MetadataJsonViewer = ({
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
    setCurrentIndex((i) => Math.max(0, i - 1));
  }, []);

  const goNext = useCallback(() => {
    setCurrentIndex((i) => {
      const next = Math.min(lines.length - 1, i + 1);
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

const getNumericField = (
  source: Record<string, unknown>,
  key: string,
): number | null => {
  const value = source[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
};

const buildGenAIMetricsPoints = (lines: string[]): GenAIMetricsPoint[] => {
  const points: GenAIMetricsPoint[] = [];

  lines.forEach((line, index) => {
    try {
      const record = JSON.parse(line) as Record<string, unknown>;
      const metrics = record.metrics;
      if (!metrics || typeof metrics !== "object" || Array.isArray(metrics)) {
        return;
      }

      const metricRecord = metrics as Record<string, unknown>;
      const ttft = getNumericField(metricRecord, "ttft_mean");
      const tpot = getNumericField(metricRecord, "tpot_mean");
      const totalLatency = getNumericField(
        metricRecord,
        "generate_duration_mean",
      );

      if (ttft === null && tpot === null && totalLatency === null) {
        return;
      }

      const timestampSeconds = getNumericField(record, "timestamp_seconds");
      const timestampNs = getNumericField(record, "timestamp");
      const timestamp =
        timestampSeconds !== null
          ? timestampSeconds * 1000
          : timestampNs !== null
            ? timestampNs / 1_000_000
            : index * 1000;

      points.push({
        timestamp,
        ttft: ttft ?? 0,
        tpot: tpot ?? 0,
        totalLatency: totalLatency ?? 0,
      });
    } catch {
      return;
    }
  });

  return points;
};

const getGenAIYAxisMax = (
  data: GenAIMetricsPoint[],
  key: keyof Pick<GenAIMetricsPoint, "ttft" | "tpot" | "totalLatency">,
) =>
  Math.ceil(
    getRecentYAxisMax(
      data.map((point) => point[key]),
      CHART_MAX_DATA_POINTS,
      100,
    ) * 1.15,
  );

const GenAIMetricsCharts = ({
  data,
  isSummary = false,
}: {
  data: GenAIMetricsPoint[];
  isSummary?: boolean;
}) => {
  if (data.length === 0) {
    return (
      <div className="min-h-[100px] flex items-center justify-center border bg-muted/20 p-3">
        <p className="text-sm text-muted-foreground">
          Waiting for VLM metrics...
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 min-w-0">
      <MetricChart
        title="VLM TTFT Over Time"
        data={data}
        dataKeys={["ttft"]}
        colors={["var(--color-orange-chart)"]}
        unit=" ms"
        yAxisDomain={[0, getGenAIYAxisMax(data, "ttft")]}
        showLegend={false}
        labels={["TTFT"]}
        maxDataPoints={CHART_MAX_DATA_POINTS}
        isSummary={isSummary}
      />
      <MetricChart
        title="VLM TPOT Over Time"
        data={data}
        dataKeys={["tpot"]}
        colors={["var(--color-green-chart)"]}
        unit=" ms"
        yAxisDomain={[0, getGenAIYAxisMax(data, "tpot")]}
        showLegend={false}
        labels={["TPOT"]}
        maxDataPoints={CHART_MAX_DATA_POINTS}
        isSummary={isSummary}
      />
      <MetricChart
        title="VLM Total Latency Over Time"
        data={data}
        dataKeys={["totalLatency"]}
        colors={["var(--color-red-chart)"]}
        unit=" ms"
        yAxisDomain={[0, getGenAIYAxisMax(data, "totalLatency")]}
        showLegend={false}
        labels={["Generation"]}
        maxDataPoints={CHART_MAX_DATA_POINTS}
        isSummary={isSummary}
      />
    </div>
  );
};

const collectMetadataStreams = (
  jobs: (Record<string, unknown> & PerformanceJobStatusWithMetadata)[],
): Record<string, string> => {
  const result: Record<string, string> = {};
  for (const job of jobs) {
    const jobId = job.id as string;
    const urls = job.metadata_stream_urls;
    if (!urls) continue;
    for (const [pipelineId, streamUrls] of Object.entries(urls)) {
      if (!Array.isArray(streamUrls) || streamUrls.length === 0) continue;
      const raw = streamUrls[0];
      const url = raw && !raw.startsWith("/api/") ? `/api/v1${raw}` : raw;
      result[`${jobId}::${pipelineId}`] = url;
    }
  }
  return result;
};

type PerformanceTestPanelProps = {
  isRunning: boolean;
  completedVideoPath: string | null;
  pipelineId?: string;
  livePreviewEnabled?: boolean;
  videoOutputEnabled?: boolean;
  enableLatencyMetrics?: boolean;
  enableMetadata?: boolean;
  liveStreamUrl?: string | null;
  resultOverrides?: FrozenSnapshotOverrides | null;
};

const PerformanceTestPanel = ({
  isRunning,
  completedVideoPath,
  pipelineId,
  livePreviewEnabled = false,
  videoOutputEnabled = false,
  enableLatencyMetrics = false,
  enableMetadata = true,
  liveStreamUrl,
  resultOverrides,
}: PerformanceTestPanelProps) => {
  const { frozenHistory, frozenSummary, startRecording, freezeSnapshot } =
    useFrozenMetrics();
  const prevIsRunningRef = useRef(false);
  const metadataSourcesRef = useRef<Record<string, EventSource>>({});
  const metadataSourceUrlsRef = useRef<Record<string, string>>({});
  const [activeMainTab, setActiveMainTab] = useState("metadata");
  const [activeMetadataTab, setActiveMetadataTab] = useState<string | null>(
    null,
  );
  const [metadataLines, setMetadataLines] = useState<Record<string, string[]>>(
    {},
  );
  const [connectionStates, setConnectionStates] = useState<
    Record<string, ConnectionState>
  >({});
  const [connectionErrors, setConnectionErrors] = useState<
    Record<string, string | null>
  >({});

  // Frozen snapshot of metadata kept after the run finishes
  const [frozenMetadata, setFrozenMetadata] = useState<{
    lines: Record<string, string[]>;
    entries: [string, string][];
  } | null>(null);

  // Poll all performance jobs to collect metadata stream URLs from ALL running jobs
  const { data: allJobs } = useGetPerformanceStatusesQuery(undefined, {
    pollingInterval: METADATA_POLL_INTERVAL,
  });

  const metadataStreamUrls = useMemo(() => {
    if (!allJobs) return {};
    const runningJobs = allJobs.filter((j) => j.state === "RUNNING");
    return collectMetadataStreams(
      runningJobs as (Record<string, unknown> &
        PerformanceJobStatusWithMetadata)[],
    );
  }, [allJobs]);

  const metadataEntries = useMemo(
    () => Object.entries(metadataStreamUrls),
    [metadataStreamUrls],
  );

  const closeMetadataSource = (pipelineKey: string) => {
    metadataSourcesRef.current[pipelineKey]?.close();
    delete metadataSourcesRef.current[pipelineKey];
    delete metadataSourceUrlsRef.current[pipelineKey];
  };

  // Auto-switch to media tab when output video becomes available (only after pipeline finishes)
  useEffect(() => {
    if (
      !isRunning &&
      completedVideoPath &&
      videoOutputEnabled &&
      !livePreviewEnabled
    ) {
      setActiveMainTab("media");
    }
  }, [isRunning, completedVideoPath, videoOutputEnabled, livePreviewEnabled]);

  useEffect(() => {
    const wasRunning = prevIsRunningRef.current;
    prevIsRunningRef.current = isRunning;

    if (!wasRunning && isRunning) {
      startRecording();
      setFrozenMetadata(null);
    } else if (wasRunning && !isRunning) {
      freezeSnapshot(resultOverrides);
      setFrozenMetadata((prev) => {
        const hasLines = Object.values(metadataLines).some((l) => l.length > 0);
        if (!hasLines) return prev;
        return { lines: { ...metadataLines }, entries: [...metadataEntries] };
      });
    }
  }, [
    isRunning,
    startRecording,
    freezeSnapshot,
    resultOverrides,
    metadataLines,
    metadataEntries,
  ]);

  useEffect(() => {
    if (metadataEntries.length === 0) {
      setActiveMetadataTab(null);
      return;
    }

    const availableKeys = new Set(
      metadataEntries.map(([pipelineKey]) => pipelineKey),
    );

    Object.keys(metadataSourcesRef.current).forEach((pipelineKey) => {
      if (!availableKeys.has(pipelineKey)) {
        closeMetadataSource(pipelineKey);

        setMetadataLines((prev) => {
          const next = { ...prev };
          delete next[pipelineKey];
          return next;
        });
        setConnectionStates((prev) => {
          const next = { ...prev };
          delete next[pipelineKey];
          return next;
        });
        setConnectionErrors((prev) => {
          const next = { ...prev };
          delete next[pipelineKey];
          return next;
        });
      }
    });

    metadataEntries.forEach(([pipelineKey, streamUrl]) => {
      const currentUrl = metadataSourceUrlsRef.current[pipelineKey];
      if (currentUrl === streamUrl && metadataSourcesRef.current[pipelineKey]) {
        return;
      }

      closeMetadataSource(pipelineKey);
      setMetadataLines((prev) => ({ ...prev, [pipelineKey]: [] }));
      setConnectionStates((prev) => ({ ...prev, [pipelineKey]: "connecting" }));
      setConnectionErrors((prev) => ({ ...prev, [pipelineKey]: null }));

      const source = new EventSource(streamUrl);
      metadataSourcesRef.current[pipelineKey] = source;
      metadataSourceUrlsRef.current[pipelineKey] = streamUrl;

      source.onopen = () => {
        setConnectionStates((prev) => ({ ...prev, [pipelineKey]: "open" }));
        setConnectionErrors((prev) => ({ ...prev, [pipelineKey]: null }));
      };

      source.onmessage = (event) => {
        const payload = event.data?.trim();
        if (!payload) {
          return;
        }

        const incomingLines = payload
          .split("\n")
          .map((line: string) => line.trim())
          .filter((line: string) => line.length > 0);

        if (incomingLines.length === 0) {
          return;
        }

        setMetadataLines((prev) => {
          const existing = prev[pipelineKey] ?? [];
          return {
            ...prev,
            [pipelineKey]: [...existing, ...incomingLines].slice(
              -MAX_JSON_LINES_PER_PIPELINE,
            ),
          };
        });
      };

      source.onerror = () => {
        const isClosed = source.readyState === EventSource.CLOSED;
        setConnectionStates((prev) => ({
          ...prev,
          [pipelineKey]: isClosed ? "closed" : "error",
        }));
        setConnectionErrors((prev) => ({
          ...prev,
          [pipelineKey]: isClosed
            ? "Metadata stream closed"
            : "Metadata stream disconnected. Reconnecting...",
        }));
      };
    });

    if (!activeMetadataTab || !availableKeys.has(activeMetadataTab)) {
      setActiveMetadataTab(metadataEntries[0][0]);
    }
  }, [activeMetadataTab, metadataEntries]);

  useEffect(() => {
    const metadataSources = metadataSourcesRef;
    const metadataSourceUrls = metadataSourceUrlsRef;

    return () => {
      Object.keys(metadataSources.current).forEach((pipelineKey) => {
        metadataSources.current[pipelineKey]?.close();
        delete metadataSources.current[pipelineKey];
        delete metadataSourceUrls.current[pipelineKey];
      });
    };
  }, []);

  const hasMetadataStreams = metadataEntries.length > 0;
  const hasStaleMetadata = !hasMetadataStreams && frozenMetadata !== null;
  const showMetadataTab = hasMetadataStreams || hasStaleMetadata;

  const displayEntries = hasMetadataStreams
    ? metadataEntries
    : (frozenMetadata?.entries ?? []);
  const displayLines = useMemo(
    () => (hasMetadataStreams ? metadataLines : (frozenMetadata?.lines ?? {})),
    [frozenMetadata?.lines, hasMetadataStreams, metadataLines],
  );

  const genAIMetricsData = useMemo(
    () =>
      Object.values(displayLines)
        .flatMap((lines) => buildGenAIMetricsPoints(lines))
        .sort((a, b) => a.timestamp - b.timestamp),
    [displayLines],
  );

  const metadataTabValue = activeMetadataTab ?? displayEntries[0]?.[0] ?? "";

  const hasMediaTab = livePreviewEnabled || videoOutputEnabled;
  const mediaTabLabel = livePreviewEnabled ? "Live Preview" : "Output Video";
  const hasLiveStream = livePreviewEnabled && (isRunning || !!liveStreamUrl);
  const hasOutputVideo =
    !livePreviewEnabled && !isRunning && !!completedVideoPath;
  const showMetadataSection = enableMetadata && showMetadataTab;
  const showGenAIMetricsTab = genAIMetricsData.length > 0;
  const showSummaryStyles = !isRunning && frozenSummary !== null;
  const visibleTabCount =
    (hasMediaTab ? 1 : 0) +
    (showMetadataSection ? 1 : 0) +
    (showGenAIMetricsTab ? 1 : 0);
  const effectiveMainTab =
    activeMainTab === "media" && !hasMediaTab
      ? showMetadataSection
        ? "metadata"
        : showGenAIMetricsTab
          ? "genai-metrics"
          : "metadata"
      : activeMainTab === "metadata" && !showMetadataSection
        ? hasMediaTab
          ? "media"
          : showGenAIMetricsTab
            ? "genai-metrics"
            : "metadata"
        : activeMainTab === "genai-metrics" && !showGenAIMetricsTab
          ? hasMediaTab
            ? "media"
            : showMetadataSection
              ? "metadata"
              : "metadata"
          : activeMainTab;

  return (
    <div className="flex flex-col w-full h-full bg-background p-4 space-y-4 overflow-y-auto overflow-x-hidden min-w-0">
      <h2 className="text-lg font-semibold">Test pipeline</h2>

      <Tabs
        value={effectiveMainTab}
        onValueChange={setActiveMainTab}
        className="flex flex-col min-w-0"
      >
        {visibleTabCount > 1 && (
          <TabsList>
            {hasMediaTab && (
              <TabsTrigger value="media">{mediaTabLabel}</TabsTrigger>
            )}
            {showMetadataSection && (
              <TabsTrigger value="metadata">Metadata JSON</TabsTrigger>
            )}
            {showGenAIMetricsTab && (
              <TabsTrigger value="genai-metrics">VLM Metrics</TabsTrigger>
            )}
          </TabsList>
        )}

        {hasMediaTab && (
          <TabsContent value="media" className="space-y-4 mt-2">
            {livePreviewEnabled && (
              <div>
                {hasLiveStream && liveStreamUrl ? (
                  <WebRTCVideoPlayer
                    pipelineId={pipelineId}
                    streamUrl={liveStreamUrl}
                  />
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Waiting for live stream to be published...
                  </p>
                )}
              </div>
            )}

            {!livePreviewEnabled && videoOutputEnabled && (
              <div>
                {hasOutputVideo && completedVideoPath ? (
                  <video
                    controls
                    className="w-full h-auto border border-gray-300"
                    src={`/assets${completedVideoPath}`}
                  >
                    Your browser does not support the video tag.
                  </video>
                ) : isRunning ? (
                  <p className="text-sm text-muted-foreground">
                    Waiting for output video...
                  </p>
                ) : null}
              </div>
            )}
          </TabsContent>
        )}

        {enableMetadata && (
          <TabsContent
            value="metadata"
            className="space-y-4 mt-2 overflow-hidden min-w-0"
          >
            {!showMetadataTab && isRunning && (
              <p className="text-sm text-muted-foreground">
                Waiting for metadata stream URLs from the API...
              </p>
            )}

            {showMetadataTab &&
              displayEntries.length === 1 &&
              (() => {
                const [compositeKey, streamUrl] = displayEntries[0];
                const lines = displayLines[compositeKey] ?? [];
                const state = hasStaleMetadata
                  ? "closed"
                  : (connectionStates[compositeKey] ?? "connecting");
                const error = hasStaleMetadata
                  ? null
                  : connectionErrors[compositeKey];
                const isStreamActive =
                  !hasStaleMetadata && state !== "error" && state !== "closed";
                return (
                  <div className="flex flex-col space-y-3 min-w-0">
                    {isStreamActive && (
                      <>
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs uppercase tracking-wide text-muted-foreground">
                            SSE: {state}
                          </span>
                        </div>
                        <a
                          href={streamUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                        >
                          {shortenStreamUrl(streamUrl)}
                          <ExternalLink className="h-3 w-3" />
                        </a>
                        {error && (
                          <p className="text-xs text-destructive">{error}</p>
                        )}
                      </>
                    )}
                    <MetadataJsonViewer
                      lines={lines}
                      stale={hasStaleMetadata}
                    />
                  </div>
                );
              })()}

            {showMetadataTab && displayEntries.length > 1 && (
              <Tabs
                value={metadataTabValue}
                onValueChange={setActiveMetadataTab}
              >
                <TabsList className="w-full h-auto flex-wrap justify-start">
                  {displayEntries.map(([compositeKey]) => {
                    const [jobId, pipelineId] = compositeKey.split("::");
                    return (
                      <TabsTrigger key={compositeKey} value={compositeKey}>
                        {buildStreamLabel(jobId, pipelineId)}
                      </TabsTrigger>
                    );
                  })}
                </TabsList>

                {displayEntries.map(([compositeKey, streamUrl], index) => {
                  const lines = displayLines[compositeKey] ?? [];
                  const state = hasStaleMetadata
                    ? "closed"
                    : (connectionStates[compositeKey] ?? "connecting");
                  const error = hasStaleMetadata
                    ? null
                    : connectionErrors[compositeKey];
                  const isStreamActive =
                    !hasStaleMetadata &&
                    state !== "error" &&
                    state !== "closed";

                  return (
                    <TabsContent
                      key={compositeKey}
                      value={compositeKey}
                      className="space-y-3 mt-4"
                    >
                      {isStreamActive && (
                        <>
                          <div className="flex items-center justify-between gap-2">
                            <h3 className="text-sm font-medium text-muted-foreground">
                              Stream {index + 1}
                            </h3>
                            <span className="text-xs uppercase tracking-wide text-muted-foreground">
                              SSE: {state}
                            </span>
                          </div>

                          <a
                            href={streamUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                          >
                            {shortenStreamUrl(streamUrl)}
                            <ExternalLink className="h-3 w-3" />
                          </a>

                          {error && (
                            <p className="text-xs text-destructive">{error}</p>
                          )}
                        </>
                      )}

                      <MetadataJsonViewer
                        lines={lines}
                        stale={hasStaleMetadata}
                      />
                    </TabsContent>
                  );
                })}
              </Tabs>
            )}
          </TabsContent>
        )}

        {showGenAIMetricsTab && (
          <TabsContent value="genai-metrics" className="space-y-4 mt-2">
            <GenAIMetricsCharts
              data={genAIMetricsData}
              isSummary={showSummaryStyles}
            />
          </TabsContent>
        )}
      </Tabs>

      {isRunning && (
        <MetricsDashboard enableLatencyMetrics={enableLatencyMetrics} />
      )}
      {!isRunning && frozenSummary && (
        <MetricsDashboard
          enableLatencyMetrics={enableLatencyMetrics}
          historyOverride={frozenHistory}
          metricsOverride={frozenSummary}
        />
      )}
    </div>
  );
};

export default PerformanceTestPanel;
