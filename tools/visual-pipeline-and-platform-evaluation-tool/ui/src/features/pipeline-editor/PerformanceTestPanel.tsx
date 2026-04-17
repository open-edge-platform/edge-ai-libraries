import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MetricsDashboard } from "@/features/metrics/MetricsDashboard.tsx";
import WebRTCVideoPlayer from "@/features/webrtc/WebRTCVideoPlayer.tsx";
import { useFrozenMetrics } from "@/hooks/useFrozenMetrics";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useGetPerformanceStatusesQuery } from "@/api/api.generated";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, ChevronsRight } from "lucide-react";

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

const prettifyJson = (raw: string): string => {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
};

const MetadataJsonViewer = ({ lines }: { lines: string[] }) => {
  const [currentIndex, setCurrentIndex] = useState(lines.length - 1);
  const [followLatest, setFollowLatest] = useState(true);

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

  if (lines.length === 0) {
    return (
      <div className="min-h-[100px] flex items-center justify-center rounded border bg-muted/20 p-3">
        <p className="text-sm text-muted-foreground">Waiting for JSON entries...</p>
      </div>
    );
  }

  const safeIndex = Math.min(currentIndex, lines.length - 1);
  const formatted = prettifyJson(lines[safeIndex]);

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
      <pre className="min-h-[100px] max-h-[400px] overflow-auto rounded border bg-muted/20 p-3 font-mono text-xs leading-5 whitespace-pre-wrap break-all">
        {formatted}
      </pre>
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
  liveStreamUrl?: string | null;
};

const PerformanceTestPanel = ({
  isRunning,
  completedVideoPath,
  pipelineId,
  livePreviewEnabled = false,
  videoOutputEnabled = false,
  liveStreamUrl,
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

  useEffect(() => {
    const wasRunning = prevIsRunningRef.current;
    prevIsRunningRef.current = isRunning;

    if (!wasRunning && isRunning) {
      startRecording();
    } else if (wasRunning && !isRunning) {
      freezeSnapshot(null);
    }
  }, [isRunning, startRecording, freezeSnapshot]);

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
          .map((line) => line.trim())
          .filter((line) => line.length > 0);

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
  const metadataTabValue = activeMetadataTab ?? metadataEntries[0]?.[0] ?? "";

  const hasMediaTab = livePreviewEnabled || videoOutputEnabled;
  const mediaTabLabel = livePreviewEnabled ? "Live Preview" : "Output Video";
  const hasLiveStream = livePreviewEnabled && (isRunning || !!liveStreamUrl);
  const hasOutputVideo = !livePreviewEnabled && !!completedVideoPath;
  const effectiveMainTab =
    activeMainTab === "media" && !hasMediaTab ? "metadata" : activeMainTab;

  return (
    <div className="flex flex-col w-full h-full bg-background p-4 space-y-4 overflow-y-auto overflow-x-hidden min-w-0">
      <h2 className="text-lg font-semibold">Test pipeline</h2>

      <Tabs
        value={effectiveMainTab}
        onValueChange={setActiveMainTab}
        className="flex flex-col min-w-0"
      >
        <TabsList>
          {hasMediaTab && (
            <TabsTrigger value="media">{mediaTabLabel}</TabsTrigger>
          )}
          <TabsTrigger value="metadata" disabled={!hasMetadataStreams}>
            Metadata JSON
          </TabsTrigger>
        </TabsList>

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
                    className="w-full h-auto border border-gray-300 rounded"
                    src={`/assets${completedVideoPath}`}
                  >
                    Your browser does not support the video tag.
                  </video>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Waiting for output video...
                  </p>
                )}
              </div>
            )}

          </TabsContent>
        )}

        <TabsContent
          value="metadata"
          className="space-y-4 mt-2 overflow-hidden min-w-0"
        >
          {!hasMetadataStreams && (
            <p className="text-sm text-muted-foreground">
              Waiting for metadata stream URLs from the API...
            </p>
          )}

          {hasMetadataStreams &&
            metadataEntries.length === 1 &&
            (() => {
              const [compositeKey, streamUrl] = metadataEntries[0];
              const lines = metadataLines[compositeKey] ?? [];
              const state = connectionStates[compositeKey] ?? "connecting";
              const error = connectionErrors[compositeKey];
              return (
                <div className="flex flex-col space-y-3 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs uppercase tracking-wide text-muted-foreground">
                      SSE: {state}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground break-all">
                    {streamUrl}
                  </p>
                  {error && <p className="text-xs text-destructive">{error}</p>}
                  <MetadataJsonViewer lines={lines} />
                </div>
              );
            })()}

          {hasMetadataStreams && metadataEntries.length > 1 && (
            <Tabs value={metadataTabValue} onValueChange={setActiveMetadataTab}>
              <TabsList className="w-full h-auto flex-wrap justify-start">
                {metadataEntries.map(([compositeKey]) => {
                  const [jobId, pipelineId] = compositeKey.split("::");
                  return (
                    <TabsTrigger key={compositeKey} value={compositeKey}>
                      {buildStreamLabel(jobId, pipelineId)}
                    </TabsTrigger>
                  );
                })}
              </TabsList>

              {metadataEntries.map(([compositeKey, streamUrl], index) => {
                const lines = metadataLines[compositeKey] ?? [];
                const state = connectionStates[compositeKey] ?? "connecting";
                const error = connectionErrors[compositeKey];

                return (
                  <TabsContent
                    key={compositeKey}
                    value={compositeKey}
                    className="space-y-3 mt-4"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <h3 className="text-sm font-medium text-muted-foreground">
                        Stream {index + 1}
                      </h3>
                      <span className="text-xs uppercase tracking-wide text-muted-foreground">
                        SSE: {state}
                      </span>
                    </div>

                    <p className="text-xs text-muted-foreground break-all">
                      {streamUrl}
                    </p>

                    {error && (
                      <p className="text-xs text-destructive">{error}</p>
                    )}

                    <MetadataJsonViewer lines={lines} />
                  </TabsContent>
                );
              })}
            </Tabs>
          )}
        </TabsContent>
      </Tabs>

      {isRunning && <MetricsDashboard />}
      {!isRunning && frozenSummary && (
        <MetricsDashboard
          historyOverride={frozenHistory}
          metricsOverride={frozenSummary}
        />
      )}
    </div>
  );
};

export default PerformanceTestPanel;
