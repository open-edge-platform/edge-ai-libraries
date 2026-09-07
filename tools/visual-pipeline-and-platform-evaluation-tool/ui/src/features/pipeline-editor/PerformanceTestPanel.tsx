import { useEffect, useMemo, useRef, useState } from "react";
import { MetadataJsonViewer } from "@/features/metadata/MetadataJsonViewer.tsx";
import { MetricsDashboard } from "@/features/metrics/MetricsDashboard.tsx";
import {
  VlmMetricsCharts,
  type VlmMetricsPoint,
} from "@/features/metrics/VlmMetricsCharts.tsx";
import WebRTCVideoPlayer from "@/features/webrtc/WebRTCVideoPlayer.tsx";
import {
  useFrozenMetrics,
  type FrozenSnapshotOverrides,
} from "@/hooks/useFrozenMetrics";
import { useMetricHistory } from "@/hooks/useMetricHistory";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useGetPerformanceStatusesQuery } from "@/api/api.generated";
import { ExternalLink } from "lucide-react";
import "@/lib/hljs-theme.css";

const MAX_JSON_LINES_PER_PIPELINE = 400;
const METADATA_POLL_INTERVAL = 3000;
type ConnectionState = "connecting" | "open" | "error" | "closed";

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
  const liveHistory = useMetricHistory();
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

  const genAIMetricsData: VlmMetricsPoint[] = useMemo(
    () =>
      (isRunning ? liveHistory : frozenHistory)
        .filter(
          (point) =>
            point.vlmTtftMs !== undefined ||
            point.vlmTpotMs !== undefined ||
            point.vlmGenerateDurationMs !== undefined,
        )
        .map((point) => ({
          timestamp: point.timestamp,
          ttft: point.vlmTtftMs ?? 0,
          tpot: point.vlmTpotMs ?? 0,
          totalLatency: point.vlmGenerateDurationMs ?? 0,
        })),
    [frozenHistory, isRunning, liveHistory],
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
            <VlmMetricsCharts
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
