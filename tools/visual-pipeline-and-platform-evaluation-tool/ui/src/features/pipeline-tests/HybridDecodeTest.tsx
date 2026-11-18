// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from "react";
import { Cpu, Play, Square } from "lucide-react";
import {
  type DensityTestSpec,
  type Pipeline,
  type PipelineGraph,
  useGetVideosQuery,
  useGetDensityJobStatusQuery,
  useRunDensityTestMutation,
  useStopDensityTestJobMutation,
} from "@/api/api.generated";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { NavigationGuard } from "@/components/shared/NavigationGuard";
import { CpuCorePinningDialog } from "@/features/pipeline-editor/CpuCorePinningDialog";
import { MetricsDashboard } from "@/features/metrics/MetricsDashboard";
import { useAsyncJob } from "@/hooks/useAsyncJob";
import { useActiveJobSync } from "@/hooks/useActiveJobSync";
import { useMetricHistory } from "@/hooks/useMetricHistory";
import { formatErrorMessage } from "@/lib/utils";
import { handleApiError, isAsyncJobError } from "@/lib/apiUtils";

const average = (values: (number | undefined)[]) => {
  const present = values.filter(
    (value): value is number => value !== undefined,
  );
  return present.length
    ? present.reduce((sum, value) => sum + value, 0) / present.length
    : undefined;
};

const isMediaFileGraph = (graph: PipelineGraph) =>
  graph.nodes.filter((node) => node.type === "filesrc").length === 1 &&
  graph.nodes.every(
    (node) =>
      !node.type.startsWith("gva") ||
      ["gvafpscounter", "gvametaconvert", "gvametapublish"].includes(node.type),
  );

export const HybridDecodeTest = ({
  pipelines,
  onRunningChange,
}: {
  pipelines: Pipeline[];
  onRunningChange: (running: boolean) => void;
}) => {
  const { data: videos = [] } = useGetVideosQuery();
  const mediaDecode = pipelines.find(
    (pipeline) =>
      pipeline.id === "media-decode" && pipeline.source === "PREDEFINED",
  );
  const variants = mediaDecode?.variants ?? [];
  const selectedHardware = variants.find(
    ({ pipeline_graph: graph }) =>
      isMediaFileGraph(graph) &&
      graph.nodes.some(
        (node) =>
          node.type === "decodebin3" &&
          node.data.caps?.includes("memory:VAMemory"),
      ),
  );
  const [videoName, setVideoName] = useState("");
  const [coreOverride, setCoreOverride] = useState<number[] | null>(null);
  const [pinningOpen, setPinningOpen] = useState(false);
  const [fpsInput, setFpsInput] = useState("30");
  const [durationInput, setDurationInput] = useState("30");
  const fps = Number(fpsInput);
  const duration = Number(durationInput);
  const [error, setError] = useState<string | null>(null);
  const [cpuUsage, setCpuUsage] = useState<Record<number, number | undefined>>(
    {},
  );
  const history = useMetricHistory(
    Number.isFinite(duration) && duration > 0
      ? duration * 1000 + 60_000
      : undefined,
  );
  const video = videos.find((entry) => entry.filename === videoName);
  const selectedSoftware = variants.find(
    ({ pipeline_graph: graph }) =>
      isMediaFileGraph(graph) &&
      graph.nodes.some((node) => node.type === `avdec_${video?.codec}`),
  );
  const cores =
    coreOverride ?? selectedSoftware?.pipeline_graph.cpu_pinning ?? [];
  const configurationError = !mediaDecode
    ? "Required Media Decode pipeline is unavailable."
    : !selectedHardware
      ? "Required Media Decode VDBox variant is unavailable."
      : video && !selectedSoftware
        ? `Required Media Decode CPU ${video.codec.toUpperCase()} variant is unavailable.`
        : null;
  const {
    execute,
    isLoading: isRunning,
    isPolling,
    jobId,
    jobStatus,
  } = useAsyncJob({
    asyncJobHook: useRunDensityTestMutation,
    statusCheckHook: useGetDensityJobStatusQuery,
  });
  const [stop, { isLoading: isStopping }] = useStopDensityTestJobMutation();
  const trials = jobStatus?.trials;
  const selected =
    !isRunning && jobStatus?.state === "COMPLETED"
      ? trials?.find((trial) => trial.index === jobStatus.selected_trial)
      : undefined;
  useActiveJobSync(jobId);
  useEffect(() => {
    onRunningChange(isRunning);
    return () => onRunningChange(false);
  }, [isRunning, onRunningChange]);

  useEffect(() => {
    if (!trials) return;
    setCpuUsage((previous) => {
      let next = previous;
      for (const trial of trials) {
        const {
          index,
          measurement_started_at: start,
          measurement_ended_at: end,
        } = trial;
        if (Object.hasOwn(previous, index) || start == null || end == null)
          continue;
        const usage = average(
          history
            .filter(
              (point) => point.timestamp >= start && point.timestamp <= end,
            )
            .map((point) => point.cpu),
        );
        if (next === previous) next = { ...previous };
        next[index] = usage;
      }
      return next;
    });
  }, [history, trials]);

  const changeVideo = (name: string) => {
    setVideoName(name);
    setCoreOverride(null);
  };
  const canRun =
    video &&
    selectedHardware &&
    selectedSoftware &&
    !configurationError &&
    Number.isInteger(fps) &&
    fps >= 1 &&
    Number.isFinite(duration) &&
    duration >= 10;
  const run = async () => {
    if (!canRun) return;
    setError(null);
    setCpuUsage({});
    const graphFor = (graph: PipelineGraph, cpu: boolean): PipelineGraph => ({
      ...graph,
      cpu_pinning: cpu ? cores : [],
      nodes: graph.nodes.map((node) =>
        node.type === "filesrc"
          ? { ...node, data: { ...node.data, location: video.filename } }
          : node,
      ),
    });
    const spec: DensityTestSpec = {
      fps_floor: fps,
      execution_config: {
        output_mode: "disabled",
        metadata_mode: "disabled",
        max_runtime: duration,
        pinned_cpu_cores: [],
      },
      pipeline_density_specs: [
        {
          pipeline: {
            source: "graph",
            graph_id: "hybrid-vdbox",
            pipeline_graph: graphFor(selectedHardware.pipeline_graph, false),
          },
          stream_rate: 50,
        },
        {
          pipeline: {
            source: "graph",
            graph_id: "hybrid-cpu",
            pipeline_graph: graphFor(selectedSoftware.pipeline_graph, true),
          },
          stream_rate: 50,
        },
      ],
    };
    try {
      await execute({ densityTestSpec: spec });
    } catch (failure) {
      setError(
        isAsyncJobError(failure)
          ? formatErrorMessage(failure.details)
          : handleApiError(failure, "Hybrid decode test failed"),
      );
    }
  };
  const counts = selected?.streams_per_pipeline;
  const hardwareCount = counts?.["hybrid-vdbox"] ?? 0;
  const cpuCount = counts?.["hybrid-cpu"] ?? 0;

  return (
    <section className="min-w-0 space-y-6" aria-label="Hybrid decode test">
      <NavigationGuard
        when={isPolling}
        title="Hybrid decode test in progress"
        description="Stop the test or wait for it to finish before leaving this page."
      />
      <div className="grid min-w-0 gap-4 md:grid-cols-2">
        <div className="min-w-0 md:col-span-2">
          <label
            htmlFor="hybrid-video"
            className="mb-1 block text-sm font-medium"
          >
            Video source
          </label>
          <Select
            value={videoName}
            onValueChange={changeVideo}
            disabled={isRunning}
          >
            <SelectTrigger id="hybrid-video" className="w-full min-w-0">
              <SelectValue placeholder="Select video" />
            </SelectTrigger>
            <SelectContent
              position="popper"
              align="start"
              className="max-h-[min(18rem,var(--radix-select-content-available-height))] w-(--radix-select-trigger-width)"
            >
              {videos
                .filter((entry) => ["h264", "h265"].includes(entry.codec))
                .map((entry) => (
                  <SelectItem key={entry.filename} value={entry.filename}>
                    {entry.filename} ·{" "}
                    {entry.codec === "h265" ? "H.265" : "H.264"}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </div>
        <dl
          aria-label="Decode configuration"
          className="grid min-w-0 gap-4 text-sm md:col-span-2"
        >
          <div>
            <dt className="font-medium">Video format</dt>
            <dd className="mt-1 text-muted-foreground">
              {video ? (video.codec === "h265" ? "H.265" : "H.264") : "-"}
            </dd>
          </div>
          <div>
            <dt className="font-medium">Hardware decoder</dt>
            <dd className="mt-1 break-words text-muted-foreground">
              {selectedHardware ? "VDBox / decodebin3" : "Unavailable"}
            </dd>
          </div>
          <div>
            <dt className="font-medium">CPU decoder</dt>
            <dd className="mt-1 break-words text-muted-foreground">
              {selectedSoftware
                ? `avdec_${video?.codec}`
                : video
                  ? "Unavailable"
                  : "-"}
            </dd>
          </div>
        </dl>
      </div>
      {configurationError && (
        <p
          role="alert"
          className="status-error border border-status-border bg-status-bg p-3 text-sm text-status-fg"
        >
          {configurationError}
        </p>
      )}
      <div className="flex flex-wrap items-end gap-6">
        <div>
          <label
            htmlFor="hybrid-fps"
            className="mb-1 block text-sm font-medium"
          >
            Target FPS
          </label>
          <Input
            id="hybrid-fps"
            type="number"
            min={1}
            value={fpsInput}
            onChange={(event) => setFpsInput(event.target.value)}
            disabled={isRunning}
            className="w-28"
          />
        </div>
        <div>
          <label
            htmlFor="hybrid-duration"
            className="mb-1 block text-sm font-medium"
          >
            Iteration duration (s)
          </label>
          <Input
            id="hybrid-duration"
            type="number"
            min={10}
            value={durationInput}
            onChange={(event) => setDurationInput(event.target.value)}
            disabled={isRunning}
            className="w-28"
          />
        </div>
        <div className="flex min-h-9 items-center gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="icon"
                aria-label="Select CPU cores"
                disabled={isRunning}
                onClick={() => setPinningOpen(true)}
              >
                <Cpu className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>CPU core pinning</TooltipContent>
          </Tooltip>
          <span className="max-w-64 break-words text-sm">
            {cores.length ? `CPU ids: ${cores.join(", ")}` : "All CPU cores"}
          </span>
        </div>
      </div>
      {isRunning ? (
        <Button
          variant="destructive"
          disabled={isStopping}
          onClick={() => jobId && stop({ jobId })}
        >
          <Square className="size-4" />
          {isStopping ? "Stopping..." : "Stop"}
        </Button>
      ) : (
        <Button onClick={run} disabled={!canRun}>
          <Play className="size-4" />
          Run hybrid decode
        </Button>
      )}
      {selected && (
        <div
          role="status"
          className="space-y-2 md border border-success/40 bg-success/5 p-4"
        >
          <h2 className="text-sm font-semibold text-success">
            Selected configuration
          </h2>
          <p className="text-lg font-semibold tabular-nums">
            VDBox {hardwareCount} + CPU {cpuCount} = {hardwareCount + cpuCount}{" "}
            streams
          </p>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm tabular-nums">
            <p>
              Slowest stream: {selected.min_stream_fps?.toFixed(2) ?? "-"} FPS
            </p>
            <p>
              CPU utilization:{" "}
              {cpuUsage[selected.index] == null
                ? "N/A"
                : `${cpuUsage[selected.index]?.toFixed(1)}%`}
            </p>
          </div>
        </div>
      )}
      {trials && trials.length > 0 && (
        <div className="min-w-0 space-y-2">
          <h2 id="hybrid-trials-heading" className="text-base font-semibold">
            Measured configurations
          </h2>
          <div
            role="region"
            aria-labelledby="hybrid-trials-heading"
            tabIndex={0}
            className="max-h-60 overflow-auto [&>[data-slot=table-container]]:overflow-visible"
          >
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-background">
                <TableRow>
                  <TableHead>Stage</TableHead>
                  <TableHead>VDBox</TableHead>
                  <TableHead>CPU</TableHead>
                  <TableHead>Total</TableHead>
                  <TableHead>Slowest FPS</TableHead>
                  <TableHead>CPU %</TableHead>
                  <TableHead>Result</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trials.map((trial) => {
                  const hardwareStreams =
                    trial.streams_per_pipeline["hybrid-vdbox"] ?? 0;
                  const cpuStreams =
                    trial.streams_per_pipeline["hybrid-cpu"] ?? 0;
                  const isBest = selected?.index === trial.index;
                  return (
                    <TableRow
                      key={trial.index}
                      className={
                        isBest
                          ? "bg-success/15 text-success hover:bg-success/20"
                          : undefined
                      }
                    >
                      <TableCell>
                        {trial.stage === "vdbox" ? "VDBox" : "CPU"}
                      </TableCell>
                      <TableCell>{hardwareStreams}</TableCell>
                      <TableCell>{cpuStreams}</TableCell>
                      <TableCell>{hardwareStreams + cpuStreams}</TableCell>
                      <TableCell>
                        {trial.min_stream_fps?.toFixed(2) ?? "-"}
                      </TableCell>
                      <TableCell>
                        {cpuUsage[trial.index]?.toFixed(1) ?? "-"}
                      </TableCell>
                      <TableCell>
                        {isBest ? (
                          <span className="font-semibold">
                            Best configuration
                          </span>
                        ) : trial.passed === null ? (
                          isRunning ? (
                            "Running"
                          ) : (
                            "Incomplete"
                          )
                        ) : trial.passed ? (
                          "At rate"
                        ) : (
                          "Below rate"
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
      {isRunning && <MetricsDashboard />}
      {error && (
        <p
          role="alert"
          className="status-error border border-status-border bg-status-bg p-3 text-sm text-status-fg"
        >
          {error}
        </p>
      )}
      <CpuCorePinningDialog
        open={pinningOpen}
        onOpenChange={setPinningOpen}
        pinnedCores={cores}
        onApply={setCoreOverride}
        allowLpeOnly
      />
    </section>
  );
};
