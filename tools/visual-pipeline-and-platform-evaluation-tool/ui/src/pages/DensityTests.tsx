import { useEffect, useState } from "react";
import {
  useFrozenMetrics,
  aggregateLatencyTracerMetrics,
} from "@/hooks/useFrozenMetrics";
import {
  type PipelineStreamSpec,
  useGetDensityJobStatusQuery,
  useRunDensityTestMutation,
  useStopDensityTestJobMutation,
} from "@/api/api.generated.ts";
import { MetricsDashboard } from "@/features/metrics/MetricsDashboard.tsx";
import { PipelineStreamsSummary } from "@/features/pipeline-tests/PipelineStreamsSummary.tsx";
import { DensityClassicPipelineSelection } from "@/features/pipeline-tests/DensityClassicPipelineSelection.tsx";
import { DensityMixedPipelineSelection } from "@/features/pipeline-tests/DensityMixedPipelineSelection.tsx";
import {
  buildClassicDensitySpecs,
  buildMixedDensitySpecs,
  createClassicSelections,
  createMixedSelections,
  DEFAULT_MIXED_STREAMS,
  isClassicSelectionValid,
  isMixedSelectionValid,
  type ClassicPipelineSelection,
  type DensityMode,
  type MixedPipelineSelection,
} from "@/features/pipeline-tests/densitySelection.ts";
import { useAppSelector } from "@/store/hooks";
import { selectPipelines } from "@/store/reducers/pipelines";
import { useAsyncJob } from "@/hooks/useAsyncJob";
import { useActiveJobSync } from "@/hooks/useActiveJobSync";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Square } from "lucide-react";
import {
  handleApiError,
  handleAsyncJobError,
  isAsyncJobError,
} from "@/lib/apiUtils.ts";
import { CONTENT_CONTAINER_CLASS, formatErrorMessage } from "@/lib/utils.ts";
import { NavigationGuard } from "@/components/shared/NavigationGuard";

export const DensityTests = () => {
  const DEFAULT_LOOPING_RUNTIME_SECONDS = 10;
  const pipelines = useAppSelector(selectPipelines);
  const [stopDensityTest, { isLoading: isStopping }] =
    useStopDensityTestJobMutation();
  const [mode, setMode] = useState<DensityMode>("classic");
  const [classicSelections, setClassicSelections] = useState<
    ClassicPipelineSelection[]
  >([]);
  const [mixedSelections, setMixedSelections] = useState<
    MixedPipelineSelection[]
  >([]);
  const [mixedStreams, setMixedStreams] = useState(DEFAULT_MIXED_STREAMS);
  const [fpsFloor, setFpsFloor] = useState<number>(30);
  const [testResult, setTestResult] = useState<{
    per_stream_fps: number | null;
    total_streams: number | null;
    streams_per_pipeline: PipelineStreamSpec[] | null;
    video_output_paths: { [key: string]: string[] } | null;
  } | null>(null);
  const [loopingEnabled, setLoopingEnabled] = useState(false);
  const [loopingRuntimeSeconds, setLoopingRuntimeSeconds] = useState(
    DEFAULT_LOOPING_RUNTIME_SECONDS,
  );
  const [loopingRuntimeInput, setLoopingRuntimeInput] = useState(
    String(DEFAULT_LOOPING_RUNTIME_SECONDS),
  );
  const [latencyMetricsEnabled, setLatencyMetricsEnabled] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const { frozenHistory, frozenSummary, startRecording, freezeSnapshot } =
    useFrozenMetrics();

  const {
    execute: runTest,
    isLoading: isRunning,
    isPolling: isPollingJob,
    jobId,
    jobStatus,
  } = useAsyncJob({
    asyncJobHook: useRunDensityTestMutation,
    statusCheckHook: useGetDensityJobStatusQuery,
  });

  useActiveJobSync(jobId);

  useEffect(() => {
    if (pipelines.length > 0 && classicSelections.length === 0) {
      setClassicSelections(createClassicSelections(pipelines));
    }
  }, [pipelines, classicSelections.length]);

  useEffect(() => {
    if (pipelines.length > 0 && mixedSelections.length === 0) {
      setMixedSelections(createMixedSelections(pipelines));
    }
  }, [pipelines, mixedSelections.length]);

  const isMixedMode = mode === "mixed";

  const canRunTest = isMixedMode
    ? isMixedSelectionValid(mixedSelections, mixedStreams)
    : isClassicSelectionValid(classicSelections);

  const handleRunTest = async () => {
    if (!canRunTest) return;

    setTestResult(null);
    setErrorMessage(null);
    startRecording();
    try {
      const status = await runTest({
        densityTestSpec: {
          execution_config: {
            output_mode: "disabled",
            max_runtime: loopingEnabled ? loopingRuntimeSeconds : 0,
            enable_latency_metrics: latencyMetricsEnabled,
          },
          fps_floor: fpsFloor,
          pipeline_density_specs: isMixedMode
            ? buildMixedDensitySpecs(mixedSelections, mixedStreams)
            : buildClassicDensitySpecs(classicSelections),
        },
      });

      setTestResult({
        per_stream_fps: status.per_stream_fps,
        total_streams: status.total_streams,
        streams_per_pipeline: status.streams_per_pipeline,
        video_output_paths: status.video_output_paths,
      });
      setErrorMessage(null);
      freezeSnapshot({
        fps: status.per_stream_fps,
        ...aggregateLatencyTracerMetrics(status.latency_tracer_metrics),
      });
    } catch (error) {
      if (isAsyncJobError(error)) {
        handleAsyncJobError(error, "Test failed");
        setErrorMessage(formatErrorMessage(error?.details, "Test failed"));
      } else {
        const errorMessage = handleApiError(error, "Test failed");
        setErrorMessage(errorMessage);
      }
      console.error("Test failed:", error);
      setTestResult(null);
      freezeSnapshot(null);
    }
  };

  const handleStopTest = async () => {
    if (!jobStatus?.id) return;

    try {
      await stopDensityTest({
        jobId: jobStatus.id,
      }).unwrap();
    } catch (err) {
      console.error("Failed to stop density test:", err);
    }
  };

  if (pipelines.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <p>Loading pipelines...</p>
      </div>
    );
  }

  return (
    <div className={CONTENT_CONTAINER_CLASS}>
      <NavigationGuard
        when={isPollingJob}
        title="Density test in progress"
        description="This page is still polling the active density test. Stop the test or wait for it to finish before leaving this page."
      />
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Density Tests</h1>
        <p className="text-muted-foreground mt-2">
          Density test finds the maximum number of streams per pipeline for the
          specified minimum FPS per stream
        </p>
      </div>

      <Tabs
        value={mode}
        onValueChange={(value) => setMode(value as DensityMode)}
        className="mb-6"
      >
        <TabsList>
          <TabsTrigger value="classic" disabled={isRunning}>
            Classic
          </TabsTrigger>
          <TabsTrigger value="mixed" disabled={isRunning}>
            Mixed
          </TabsTrigger>
        </TabsList>

        <TabsContent value="classic">
          <p className="text-sm text-muted-foreground mb-3">
            Streams are distributed across pipelines according to participation
            rates summing up to 100%.
          </p>
          <DensityClassicPipelineSelection
            pipelines={pipelines}
            selections={classicSelections}
            onSelectionsChange={setClassicSelections}
            disabled={isRunning}
          />
        </TabsContent>

        <TabsContent value="mixed">
          <p className="text-sm text-muted-foreground mb-3">
            Exactly two pipelines. The first pipeline runs a fixed number of
            streams, the second one is incremented by the benchmark algorithm
            until the target FPS is no longer met.
          </p>
          <DensityMixedPipelineSelection
            pipelines={pipelines}
            selections={mixedSelections}
            onSelectionsChange={setMixedSelections}
            streams={mixedStreams}
            onStreamsChange={setMixedStreams}
            disabled={isRunning}
          />
        </TabsContent>
      </Tabs>

      <div className="my-4">
        <label className="block text-sm font-medium mb-2">Set target FPS</label>
        <div className="flex items-center gap-3">
          <input
            type="number"
            value={fpsFloor}
            onChange={(e) => setFpsFloor(Number(e.target.value))}
            min={1}
            max={120}
            disabled={isRunning}
            className="w-24 px-3 py-2 border"
          />
          <span className="text-sm text-muted-foreground">FPS</span>
        </div>

        <div className="my-4 flex items-center gap-6 flex-wrap">
          <div className="flex items-center">
            <Tooltip>
              <TooltipTrigger asChild>
                <label className="flex items-center gap-2 cursor-pointer h-[2.625rem]">
                  <Checkbox
                    checked={latencyMetricsEnabled}
                    disabled={isRunning}
                    onCheckedChange={(checked) =>
                      setLatencyMetricsEnabled(checked === true)
                    }
                  />
                  <span className="text-sm font-medium">
                    Enable latency metrics
                  </span>
                </label>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p>Collect pipeline latency measurements during the test</p>
              </TooltipContent>
            </Tooltip>
          </div>

          <div className="flex items-center">
            <Tooltip>
              <TooltipTrigger asChild>
                <label className="flex items-center gap-2 cursor-pointer h-[42px]">
                  <Checkbox
                    checked={loopingEnabled}
                    disabled={isRunning}
                    onCheckedChange={(checked) => {
                      const isChecked = checked === true;
                      setLoopingEnabled(isChecked);
                    }}
                  />
                  <span className="text-sm font-medium">
                    Set iteration duration
                  </span>
                </label>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p>Run test iteration for a selected duration</p>
              </TooltipContent>
            </Tooltip>
          </div>

          {loopingEnabled && (
            <div className="flex items-center gap-2 h-[2.625rem]">
              <span className="text-xs text-muted-foreground">Duration</span>
              <Input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                value={loopingRuntimeInput}
                disabled={isRunning}
                onChange={(event) => {
                  const value = event.target.value;

                  if (value !== "" && !/^\d+$/.test(value)) {
                    return;
                  }

                  setLoopingRuntimeInput(value);

                  if (value === "") {
                    return;
                  }

                  const parsedValue = Number.parseInt(value, 10);
                  setLoopingRuntimeSeconds(parsedValue);
                }}
                onBlur={() => {
                  const parsedValue =
                    loopingRuntimeInput.trim().length === 0
                      ? Number.NaN
                      : Number.parseInt(loopingRuntimeInput, 10);
                  const normalizedValue =
                    Number.isFinite(parsedValue) && parsedValue >= 1
                      ? parsedValue
                      : DEFAULT_LOOPING_RUNTIME_SECONDS;

                  setLoopingRuntimeSeconds(normalizedValue);
                  setLoopingRuntimeInput(String(normalizedValue));
                }}
                className="h-8 w-24 px-2 text-xs"
              />
              <span className="text-xs text-muted-foreground">s</span>
            </div>
          )}
        </div>

        {isRunning ? (
          <Button
            onClick={handleStopTest}
            disabled={isStopping}
            variant="destructive"
            className="w-[10rem]"
            title="Stop test"
          >
            <Square className="w-5 h-5" />
            <span>{isStopping ? "Stopping..." : "Stop"}</span>
          </Button>
        ) : (
          <Button onClick={handleRunTest} disabled={isRunning || !canRunTest}>
            {isRunning ? "Starting..." : "Run density test"}
          </Button>
        )}

        {jobStatus && (
          <div className="status-info m-4 p-3 bg-status-bg border border-status-border">
            <p className="text-sm font-medium text-status-fg">
              Test Status: {jobStatus.state}
            </p>
            {jobStatus.state === "RUNNING" && (
              <div className="mt-2">
                <div className="animate-pulse flex items-center gap-2">
                  <div className="h-2 w-2 bg-status-info-accent"></div>
                  <span className="text-xs text-status-fg">
                    Running density test...
                  </span>
                </div>
                <MetricsDashboard
                  enableLatencyMetrics={latencyMetricsEnabled}
                />
              </div>
            )}
          </div>
        )}

        {testResult && (
          <div className="status-success m-4 p-3 bg-status-bg border border-status-border">
            <p className="text-sm font-medium text-status-fg mb-2">
              Test Completed Successfully
            </p>
            <div className="space-y-1 text-sm">
              <p className="text-status-fg">
                <span className="font-medium">Per Stream FPS:</span>{" "}
                {testResult.per_stream_fps?.toFixed(2) ?? "N/A"}
              </p>
              <p className="text-status-fg">
                <span className="font-medium">Total Streams:</span>{" "}
                {testResult.total_streams ?? "N/A"}
              </p>
              {testResult.streams_per_pipeline && (
                <div className="mt-2">
                  <p className="text-status-fg font-medium mb-1">
                    Streams per Pipeline:
                  </p>
                  <PipelineStreamsSummary
                    streamsPerPipeline={testResult.streams_per_pipeline}
                    pipelines={pipelines ?? []}
                  />
                </div>
              )}
            </div>
          </div>
        )}

        {!isRunning && frozenSummary && (
          <div className="status-info m-4 p-3 bg-status-bg border border-status-border">
            <p className="text-sm font-medium text-status-fg mb-2">
              Frozen Metrics Snapshot
            </p>
            <MetricsDashboard
              historyOverride={frozenHistory}
              metricsOverride={frozenSummary}
            />
          </div>
        )}

        {errorMessage && (
          <div className="status-error my-4 p-3 bg-status-bg border border-status-border">
            <p className="text-sm font-medium text-status-fg mb-2">
              Test Failed
            </p>
            <p className="text-xs text-status-fg">{errorMessage}</p>
          </div>
        )}
      </div>
      <div className="pb-4" />
    </div>
  );
};
