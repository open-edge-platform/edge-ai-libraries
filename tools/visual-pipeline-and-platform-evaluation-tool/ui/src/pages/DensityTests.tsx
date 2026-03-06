import { useEffect, useState } from "react";
import {
  type PipelineStreamSpec,
  useGetDensityJobStatusQuery,
  useRunDensityTestMutation,
  useStopDensityTestJobMutation,
} from "@/api/api.generated.ts";
import { TestProgressIndicator } from "@/features/pipeline-tests/TestProgressIndicator.tsx";
import { PipelineStreamsSummary } from "@/features/pipeline-tests/PipelineStreamsSummary.tsx";
import { useAppSelector } from "@/store/hooks";
import { selectPipelines } from "@/store/reducers/pipelines";
import { useAsyncJob } from "@/hooks/useAsyncJob";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Square, Plus, X } from "lucide-react";
import { ParticipationSlider } from "@/features/pipeline-tests/ParticipationSlider.tsx";
import {
  handleApiError,
  handleAsyncJobError,
  isAsyncJobError,
} from "@/lib/apiUtils.ts";
import { formatErrorMessage } from "@/lib/utils.ts";
import { useStreamRateChange } from "@/hooks/useStreamRateChange.ts";

interface PipelineSelection {
  pipelineId: string;
  variantId: string;
  stream_rate: number;
  isRemoving?: boolean;
  isNew?: boolean;
}

export const DensityTests = () => {
  const DEFAULT_LOOPING_RUNTIME_SECONDS = 60;
  const pipelines = useAppSelector(selectPipelines);
  const [stopDensityTest, { isLoading: isStopping }] =
    useStopDensityTestJobMutation();
  const [pipelineSelections, setPipelineSelections] = useState<
    PipelineSelection[]
  >([]);
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
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const handleStreamRateChange = useStreamRateChange(setPipelineSelections);

  const {
    execute: runTest,
    isLoading: isRunning,
    jobStatus,
  } = useAsyncJob({
    asyncJobHook: useRunDensityTestMutation,
    statusCheckHook: useGetDensityJobStatusQuery,
  });

  useEffect(() => {
    if (pipelines.length > 0 && pipelineSelections.length === 0) {
      const firstPipeline = pipelines[0];
      const firstVariant = firstPipeline.variants[0];
      setPipelineSelections([
        {
          pipelineId: firstPipeline.id,
          variantId: firstVariant.id,
          stream_rate: 100,
          isNew: false,
        },
      ]);
    }
  }, [pipelines, pipelineSelections.length]);

  const handleAddPipeline = () => {
    const usedPipelineIds = pipelineSelections.map((sel) => sel.pipelineId);
    const availablePipeline = pipelines.find(
      (pipeline) => !usedPipelineIds.includes(pipeline.id),
    );
    if (availablePipeline) {
      const firstVariant = availablePipeline.variants[0];
      if (!firstVariant) return;

      setPipelineSelections((prev) => {
        const next = [
          ...prev,
          {
            pipelineId: availablePipeline.id,
            variantId: firstVariant.id,
            stream_rate: 0,
            isNew: true,
          },
        ];

        const count = next.length;
        const baseRate = Math.floor(100 / count);
        const remainder = 100 - baseRate * count;

        return next.map((selection, index) => ({
          ...selection,
          stream_rate: index === 0 ? baseRate + remainder : baseRate,
        }));
      });
      setTimeout(() => {
        setPipelineSelections((prev) =>
          prev.map((sel, idx) =>
            idx === prev.length - 1 ? { ...sel, isNew: false } : sel,
          ),
        );
      }, 300);
    }
  };

  const handleRemovePipeline = (pipelineId: string) => {
    if (pipelineSelections.length > 1) {
      setPipelineSelections((prev) =>
        prev.map((sel) =>
          sel.pipelineId === pipelineId ? { ...sel, isRemoving: true } : sel,
        ),
      );
      setTimeout(() => {
        setPipelineSelections((prev) => {
          const filtered = prev.filter((sel) => sel.pipelineId !== pipelineId);

          if (filtered.length === 0) return filtered;

          const count = filtered.length;
          const baseRate = Math.floor(100 / count);
          const remainder = 100 - baseRate * count;

          return filtered.map((selection, index) => ({
            ...selection,
            stream_rate: index === 0 ? baseRate + remainder : baseRate,
          }));
        });
      }, 300);
    }
  };

  const handlePipelineChange = (index: number, newPipelineId: string) => {
    setPipelineSelections((prev) =>
      prev.map((sel, idx) => {
        if (idx === index) {
          const newPipeline = pipelines.find((p) => p.id === newPipelineId);
          const firstVariant = newPipeline?.variants[0];
          return {
            ...sel,
            pipelineId: newPipelineId,
            variantId: firstVariant?.id || sel.variantId,
          };
        }
        return sel;
      }),
    );
  };

  const handleVariantChange = (index: number, newVariantId: string) => {
    setPipelineSelections((prev) =>
      prev.map((sel, idx) =>
        idx === index ? { ...sel, variantId: newVariantId } : sel,
      ),
    );
  };

  const handleRunTest = async () => {
    if (pipelineSelections.length === 0) return;

    setTestResult(null);
    setErrorMessage(null);
    try {
      const status = await runTest({
        densityTestSpec: {
          execution_config: {
            output_mode: "disabled",
            max_runtime: loopingEnabled ? loopingRuntimeSeconds : 0,
          },
          fps_floor: fpsFloor,
          pipeline_density_specs: pipelineSelections.map((selection) => ({
            pipeline: {
              source: "variant",
              pipeline_id: selection.pipelineId,
              variant_id: selection.variantId,
            },
            stream_rate: selection.stream_rate,
          })),
        },
      });

      setTestResult({
        per_stream_fps: status.per_stream_fps,
        total_streams: status.total_streams,
        streams_per_pipeline: status.streams_per_pipeline,
        video_output_paths: status.video_output_paths,
      });
      setErrorMessage(null);
    } catch (error) {
      if (isAsyncJobError(error)) {
        handleAsyncJobError(error, "Test failed");
        setErrorMessage(
          formatErrorMessage(error?.error_message, "Test failed"),
        );
      } else {
        const errorMessage = handleApiError(error, "Test failed");
        setErrorMessage(errorMessage);
      }
      console.error("Test failed:", error);
      setTestResult(null);
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
    <div className="container mx-auto py-10">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Density Tests</h1>
        <p className="text-muted-foreground mt-2">
          Density test finds the maximum number of streams per pipeline for the
          specified minimum FPS per stream
        </p>
      </div>

      <div className="space-y-3 mb-6">
        {pipelineSelections.map((selection, index) => {
          const selectedPipeline = pipelines.find(
            (p) => p.id === selection.pipelineId,
          );
          return (
            <div
              key={`${selection.pipelineId}-${index}`}
              className={`flex items-center gap-3 p-2 border bg-card transition-all duration-300 ${
                selection.isRemoving
                  ? "opacity-0 -translate-y-2"
                  : selection.isNew
                    ? "animate-in fade-in slide-in-from-top-2"
                    : ""
              }`}
            >
              <div className="flex-1 flex items-center gap-4">
                <div className="flex-1">
                  <label className="block text-sm font-medium mb-1">
                    Pipeline
                  </label>
                  <Select
                    value={selection.pipelineId}
                    onValueChange={(value) =>
                      handlePipelineChange(index, value)
                    }
                    disabled={isRunning}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {pipelines.map((pipeline) => (
                        <SelectItem key={pipeline.id} value={pipeline.id}>
                          {pipeline.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex-1">
                  <label className="block text-sm font-medium mb-1">
                    Variant
                  </label>
                  <Select
                    value={selection.variantId}
                    onValueChange={(value) => handleVariantChange(index, value)}
                    disabled={isRunning}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {selectedPipeline?.variants.map((variant) => (
                        <SelectItem key={variant.id} value={variant.id}>
                          {variant.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex-1">
                  <label className="block text-sm font-medium mb-1">
                    Participation Rate
                  </label>
                  <ParticipationSlider
                    value={selection.stream_rate}
                    onChange={(val) =>
                      handleStreamRateChange(selection.pipelineId, val)
                    }
                    min={0}
                    max={100}
                    disabled={isRunning}
                  />
                </div>
              </div>

              {pipelineSelections.length > 1 && (
                <Button
                  onClick={() => handleRemovePipeline(selection.pipelineId)}
                  variant="ghost"
                  size="icon"
                  className="text-destructive"
                  disabled={isRunning}
                >
                  <X className="w-5 h-5" />
                </Button>
              )}
            </div>
          );
        })}

        <Button
          onClick={handleAddPipeline}
          variant="outline"
          disabled={
            pipelineSelections.length >= pipelines.length || isRunning
          }
        >
          <Plus className="w-5 h-5" />
          <span>Add Pipeline</span>
        </Button>
      </div>

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

        <div className="my-4 flex flex-col">
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
                    Run pipeline in loop
                  </span>
                </label>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p>Run test in loop mode for a selected duration</p>
              </TooltipContent>
            </Tooltip>
          </div>

          {loopingEnabled && (
            <div className="ml-6 flex items-center gap-2">
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
            className="w-[160px]"
            title="Stop test"
          >
            <Square className="w-5 h-5" />
            <span>{isStopping ? "Stopping..." : "Stop"}</span>
          </Button>
        ) : (
          <Button
            onClick={handleRunTest}
            disabled={isRunning || pipelineSelections.length === 0}
          >
            {isRunning ? "Starting..." : "Run density test"}
          </Button>
        )}

        {jobStatus && (
          <div className="m-4 p-3 bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800">
            <p className="text-sm font-medium text-blue-900 dark:text-blue-100">
              Test Status: {jobStatus.state}
            </p>
            {jobStatus.state === "RUNNING" && (
              <div className="mt-2">
                <div className="animate-pulse flex items-center gap-2">
                  <div className="h-2 w-2 bg-blue-500"></div>
                  <span className="text-xs text-blue-700 dark:text-blue-300">
                    Running density test...
                  </span>
                </div>
                <TestProgressIndicator />
              </div>
            )}
          </div>
        )}

        {errorMessage && (
          <div className="my-4 p-3 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800">
            <p className="text-sm font-medium text-red-900 dark:text-red-100 mb-2">
              Test Failed
            </p>
            <p className="text-xs text-red-700 dark:text-red-300">
              {errorMessage}
            </p>
          </div>
        )}

        {testResult && (
          <div className="my-4 p-3 bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800">
            <p className="text-sm font-medium text-green-900 dark:text-green-100 mb-2">
              Test Completed Successfully
            </p>
            <div className="space-y-1 text-sm">
              <p className="text-green-800 dark:text-green-200">
                <span className="font-medium">Per Stream FPS:</span>{" "}
                {testResult.per_stream_fps?.toFixed(2) ?? "N/A"}
              </p>
              <p className="text-green-800 dark:text-green-200">
                <span className="font-medium">Total Streams:</span>{" "}
                {testResult.total_streams ?? "N/A"}
              </p>
              {testResult.streams_per_pipeline && (
                <div className="mt-2">
                  <p className="text-green-800 dark:text-green-200 font-medium mb-1">
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
      </div>
    </div>
  );
};
