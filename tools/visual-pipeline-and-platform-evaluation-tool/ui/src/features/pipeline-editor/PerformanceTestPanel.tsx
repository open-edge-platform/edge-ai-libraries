import { useEffect, useMemo, useRef, useState } from "react";
import { MetadataJsonViewer } from "@/features/metadata/MetadataJsonViewer.tsx";
import { MetricsDashboard } from "@/features/metrics/MetricsDashboard.tsx";
import {
  VlmMetricsCharts,
  type VlmMetricsPoint,
} from "@/features/metrics/VlmMetricsCharts.tsx";
import WebRTCVideoPlayer from "@/features/webrtc/WebRTCVideoPlayer.tsx";
import { LivePipelineEvents } from "@/features/pipeline-editor/LivePipelineEvents.tsx";
import {
  useFrozenMetrics,
  type FrozenSnapshotOverrides,
} from "@/hooks/useFrozenMetrics";
import { useMetricHistory } from "@/hooks/useMetricHistory";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { PerformanceJobStatus, PipelineEvent } from "@/api/api.generated";
import { ExternalLink } from "lucide-react";
import "@/lib/hljs-theme.css";

const MAX_JSON_LINES_PER_PIPELINE = 400;
type ConnectionState = "connecting" | "open" | "error" | "closed";

/** Shorten a stream URL to its last two meaningful path segments. */
const shortenStreamUrl = (url: string): string => {
  const segments = url.replace(/\/+$/, "").split("/").filter(Boolean);
  return segments.length > 2 ? `…/${segments.slice(-2).join("/")}` : url;
};

const collectMetadataStreamUrls = (
  urls: PerformanceJobStatus["metadata_stream_urls"] | undefined,
): string[] =>
  Object.values(urls ?? {})
    .flat()
    .filter(Boolean)
    .map((raw) => (raw.startsWith("/api/") ? raw : `/api/v1${raw}`));

type PerformanceTestPanelProps = {
  isRunning: boolean;
  completedVideoPath: string | null;
  metadataStreamUrls?: PerformanceJobStatus["metadata_stream_urls"];
  pipelineId?: string;
  livePreviewEnabled?: boolean;
  videoOutputEnabled?: boolean;
  enableLatencyMetrics?: boolean;
  enableMetadata?: boolean;
  isVlmPipeline?: boolean;
  isAlertingVlmPipeline?: boolean;
  liveStreamUrl?: string | null;
  resultOverrides?: FrozenSnapshotOverrides | null;
  events?: PipelineEvent[];
};

const PerformanceTestPanel = ({
  isRunning,
  completedVideoPath,
  metadataStreamUrls: jobMetadataStreamUrls,
  pipelineId,
  livePreviewEnabled = false,
  videoOutputEnabled = false,
  enableLatencyMetrics = false,
  enableMetadata = true,
  isVlmPipeline = false,
  isAlertingVlmPipeline = false,
  liveStreamUrl,
  resultOverrides,
  events,
}: PerformanceTestPanelProps) => {
  const { frozenHistory, frozenSummary, startRecording, freezeSnapshot } =
    useFrozenMetrics();
  const liveHistory = useMetricHistory();
  const prevIsRunningRef = useRef(false);
  const metadataSourcesRef = useRef<Record<string, EventSource>>({});
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
  // Last non-empty events list, kept visible after the job status stops polling.
  const [displayedEvents, setDisplayedEvents] = useState<PipelineEvent[]>([]);

  useEffect(() => {
    if (events && events.length > 0) {
      setDisplayedEvents(events);
    }
  }, [events]);

  // Frozen snapshot of metadata kept after the run finishes
  const [frozenMetadata, setFrozenMetadata] = useState<{
    lines: Record<string, string[]>;
    urls: string[];
  } | null>(null);

  const metadataStreamUrls = useMemo(
    () =>
      isRunning && enableMetadata
        ? collectMetadataStreamUrls(jobMetadataStreamUrls)
        : [],
    [isRunning, enableMetadata, jobMetadataStreamUrls],
  );

  const closeMetadataSource = (streamUrl: string) => {
    metadataSourcesRef.current[streamUrl]?.close();
    delete metadataSourcesRef.current[streamUrl];
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
      setDisplayedEvents(events?.length ? events : []);
    } else if (wasRunning && !isRunning) {
      freezeSnapshot(resultOverrides);
      const urls = Object.keys(metadataSourcesRef.current);
      setFrozenMetadata((prev) => {
        const hasLines = Object.values(metadataLines).some((l) => l.length > 0);
        if (!hasLines) return prev;
        return { lines: { ...metadataLines }, urls };
      });
    }
  }, [
    isRunning,
    startRecording,
    freezeSnapshot,
    resultOverrides,
    events,
    metadataLines,
  ]);

  useEffect(() => {
    if (metadataStreamUrls.length === 0) {
      if (!frozenMetadata) {
        setActiveMetadataTab(null);
      }
      return;
    }

    const availableUrls = new Set(metadataStreamUrls);

    Object.keys(metadataSourcesRef.current).forEach((streamUrl) => {
      if (!availableUrls.has(streamUrl)) {
        closeMetadataSource(streamUrl);

        setMetadataLines((prev) => {
          const next = { ...prev };
          delete next[streamUrl];
          return next;
        });
        setConnectionStates((prev) => {
          const next = { ...prev };
          delete next[streamUrl];
          return next;
        });
        setConnectionErrors((prev) => {
          const next = { ...prev };
          delete next[streamUrl];
          return next;
        });
      }
    });

    metadataStreamUrls.forEach((streamUrl) => {
      if (metadataSourcesRef.current[streamUrl]) {
        return;
      }

      setMetadataLines((prev) => ({ ...prev, [streamUrl]: [] }));
      setConnectionStates((prev) => ({ ...prev, [streamUrl]: "connecting" }));
      setConnectionErrors((prev) => ({ ...prev, [streamUrl]: null }));

      const source = new EventSource(streamUrl);
      metadataSourcesRef.current[streamUrl] = source;

      source.onopen = () => {
        setConnectionStates((prev) => ({ ...prev, [streamUrl]: "open" }));
        setConnectionErrors((prev) => ({ ...prev, [streamUrl]: null }));
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
          const existing = prev[streamUrl] ?? [];
          return {
            ...prev,
            [streamUrl]: [...existing, ...incomingLines].slice(
              -MAX_JSON_LINES_PER_PIPELINE,
            ),
          };
        });
      };

      source.onerror = () => {
        const isClosed = source.readyState === EventSource.CLOSED;
        setConnectionStates((prev) => ({
          ...prev,
          [streamUrl]: isClosed ? "closed" : "error",
        }));
        setConnectionErrors((prev) => ({
          ...prev,
          [streamUrl]: isClosed
            ? "Metadata stream closed"
            : "Metadata stream disconnected. Reconnecting...",
        }));
      };
    });

    if (!activeMetadataTab || !availableUrls.has(activeMetadataTab)) {
      setActiveMetadataTab(metadataStreamUrls[0]);
    }
  }, [activeMetadataTab, frozenMetadata, metadataStreamUrls]);

  useEffect(() => {
    const metadataSources = metadataSourcesRef;

    return () => {
      Object.keys(metadataSources.current).forEach((streamUrl) => {
        metadataSources.current[streamUrl]?.close();
        delete metadataSources.current[streamUrl];
      });
    };
  }, []);

  const hasMetadataStreams = metadataStreamUrls.length > 0;
  const hasStaleMetadata = !hasMetadataStreams && frozenMetadata !== null;
  const showMetadataTab = hasMetadataStreams || hasStaleMetadata;

  const displayUrls = hasMetadataStreams
    ? metadataStreamUrls
    : (frozenMetadata?.urls ?? []);
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

  const metadataTabValue = activeMetadataTab ?? displayUrls[0] ?? "";

  const hasMediaTab = livePreviewEnabled || videoOutputEnabled;
  const mediaTabLabel = livePreviewEnabled ? "Live Preview" : "Output Video";
  const hasLiveStream = livePreviewEnabled && (isRunning || !!liveStreamUrl);
  const hasOutputVideo =
    !livePreviewEnabled && !isRunning && !!completedVideoPath;
  const showMetadataSection = enableMetadata && showMetadataTab;
  const showSummaryStyles = !isRunning && frozenSummary !== null;

  const availableMainTabs = useMemo(() => {
    const tabs: string[] = [];
    if (hasMediaTab) tabs.push("media");
    if (showMetadataSection) tabs.push("metadata");
    return tabs;
  }, [hasMediaTab, showMetadataSection]);

  // Snap `activeMainTab` back to the first available tab whenever the current
  // one disappears (e.g. a metadata stream ends).
  useEffect(() => {
    if (
      availableMainTabs.length > 0 &&
      !availableMainTabs.includes(activeMainTab)
    ) {
      setActiveMainTab(availableMainTabs[0]);
    }
  }, [availableMainTabs, activeMainTab]);

  return (
    <div className="flex flex-col w-full h-full bg-background p-4 space-y-4 overflow-y-auto overflow-x-hidden min-w-0">
      <h2 className="text-lg font-semibold">Test pipeline</h2>

      <Tabs
        value={activeMainTab}
        onValueChange={setActiveMainTab}
        className="flex flex-col min-w-0"
      >
        {availableMainTabs.length > 1 && (
          <TabsList className="grid w-full grid-flow-col auto-cols-fr">
            {hasMediaTab && (
              <TabsTrigger value="media">{mediaTabLabel}</TabsTrigger>
            )}
            {showMetadataSection && (
              <TabsTrigger value="metadata">Metadata JSON</TabsTrigger>
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

            {displayedEvents.length > 0 && (
              <LivePipelineEvents
                events={displayedEvents}
                isRunning={isRunning}
                title="Video captions"
                showTriggeredCount={!isVlmPipeline}
                highlightAlerts={isAlertingVlmPipeline}
              />
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
              displayUrls.length === 1 &&
              (() => {
                const streamUrl = displayUrls[0];
                const lines = displayLines[streamUrl] ?? [];
                const state = hasStaleMetadata
                  ? "closed"
                  : (connectionStates[streamUrl] ?? "connecting");
                const error = hasStaleMetadata
                  ? null
                  : connectionErrors[streamUrl];
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

            {showMetadataTab && displayUrls.length > 1 && (
              <Tabs
                value={metadataTabValue}
                onValueChange={setActiveMetadataTab}
              >
                <TabsList className="grid h-10 w-full grid-cols-[repeat(auto-fit,minmax(min(100%,7rem),1fr))] items-stretch gap-0 rounded-none border-b border-border bg-transparent p-0">
                  {displayUrls.map((streamUrl, index) => {
                    return (
                      <TabsTrigger
                        key={streamUrl}
                        value={streamUrl}
                        className="h-full w-full min-w-0 flex-1 self-stretch rounded-none border-0 border-b-2 border-transparent px-3 text-sm after:hidden data-[state=active]:border-primary data-[state=active]:bg-primary/5 data-[state=active]:text-primary data-[state=active]:shadow-none"
                      >
                        Stream {index + 1}
                      </TabsTrigger>
                    );
                  })}
                </TabsList>

                {displayUrls.map((streamUrl, index) => {
                  const lines = displayLines[streamUrl] ?? [];
                  const state = hasStaleMetadata
                    ? "closed"
                    : (connectionStates[streamUrl] ?? "connecting");
                  const error = hasStaleMetadata
                    ? null
                    : connectionErrors[streamUrl];
                  const isStreamActive =
                    !hasStaleMetadata &&
                    state !== "error" &&
                    state !== "closed";

                  return (
                    <TabsContent
                      key={streamUrl}
                      value={streamUrl}
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
      </Tabs>

      {isRunning && (
        <MetricsDashboard enableLatencyMetrics={enableLatencyMetrics}>
          {genAIMetricsData.length > 0 && (
            <VlmMetricsCharts data={genAIMetricsData} />
          )}
        </MetricsDashboard>
      )}
      {!isRunning && frozenSummary && (
        <MetricsDashboard
          enableLatencyMetrics={enableLatencyMetrics}
          historyOverride={frozenHistory}
          metricsOverride={frozenSummary}
        >
          {genAIMetricsData.length > 0 && (
            <VlmMetricsCharts
              data={genAIMetricsData}
              isSummary={showSummaryStyles}
            />
          )}
        </MetricsDashboard>
      )}
    </div>
  );
};

export default PerformanceTestPanel;
