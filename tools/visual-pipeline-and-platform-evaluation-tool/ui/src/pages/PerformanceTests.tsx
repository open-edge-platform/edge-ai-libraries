import { useEffect, useState } from "react";
import {
  useGetPerformanceJobStatusQuery,
  useRunPerformanceTestMutation,
} from "@/api/api.generated";
import { TestProgressIndicator } from "@/features/pipeline-tests/TestProgressIndicator.tsx";
import { PipelineName } from "@/features/pipelines/PipelineName.tsx";
import { useAppSelector } from "@/store/hooks";
import { selectPipelines } from "@/store/reducers/pipelines";
import { useAsyncJob } from "@/hooks/useAsyncJob";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Plus, X } from "lucide-react";
import { StreamsSlider } from "@/features/pipeline-tests/StreamsSlider.tsx";
import SaveOutputWarning from "@/features/pipeline-tests/SaveOutputWarning.tsx";
import {
  handleApiError,
  handleAsyncJobError,
  isAsyncJobError,
} from "@/lib/apiUtils";
import { formatErrorMessage } from "@/lib/utils.ts";

interface PipelineSelection {
  pipelineId: string;
  variantId: string;
  streams: number;
  isRemoving?: boolean;
  isNew?: boolean;
}

export const PerformanceTests = () => {
  const pipelines = useAppSelector(selectPipelines);
  const [pipelineSelections, setPipelineSelections] = useState<
    PipelineSelection[]
  >([]);
  const [testResult, setTestResult] = useState<{
    total_fps: number | null;
    per_stream_fps: number | null;
    video_output_paths: {
      [key: string]: string[];
    } | null;
  } | null>(null);
  const [videoOutputEnabled, setVideoOutputEnabled] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const {
    execute: runTest,
    isLoading,
    jobStatus,
  } = useAsyncJob({
    asyncJobHook: useRunPerformanceTestMutation,
    statusCheckHook: useGetPerformanceJobStatusQuery,
  });

  useEffect(() => {
    if (pipelines.length > 0 && pipelineSelections.length === 0) {
      const firstPipeline = pipelines[0];
      const firstVariant = firstPipeline.variants[0];
      setPipelineSelections([
        {
          pipelineId: firstPipeline.id,
          variantId: firstVariant.id,
          streams: 8,
          isNew: false,
        },
      ]);
    }
  }, [pipelines, pipelineSelections.length]);

  const handleAddPipeline = () => {
    if (pipelines.length > 0) {
      const firstPipeline = pipelines[0];
      const firstVariant = firstPipeline.variants[0];
      setPipelineSelections((prev) => [
        ...prev,
        {
          pipelineId: firstPipeline.id,
          variantId: firstVariant.id,
          streams: 8,
          isNew: true,
        },
      ]);
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
        setPipelineSelections((prev) =>
          prev.filter((sel) => sel.pipelineId !== pipelineId),
        );
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

  const handleStreamsChange = (index: number, streams: number) => {
    setPipelineSelections((prev) =>
      prev.map((sel, idx) => (idx === index ? { ...sel, streams } : sel)),
    );
  };

  const handleRunTest = async () => {
    setTestResult(null);
    setErrorMessage(null);
    try {
      const status = await runTest({
        performanceTestSpec: {
          execution_config: {
            output_mode: videoOutputEnabled ? "file" : "disabled",
            max_runtime: 0,
          },
          pipeline_performance_specs: pipelineSelections.map((selection) => ({
            pipeline: {
              source: "variant",
              pipeline_id: selection.pipelineId,
              variant_id: selection.variantId,
            },
            streams: selection.streams,
          })),
        },
      });

      setTestResult({
        total_fps: status.total_fps,
        per_stream_fps: status.per_stream_fps,
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

  if (pipelines.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <p>Loading pipelines...</p>
      </div>
    );
  }

  return (
    <>
      <div className="container mx-auto py-10">
        <div className="mb-6">
          <h1 className="text-3xl font-bold">Performance Tests</h1>
          <p className="text-muted-foreground mt-2">
            Performance test measures total and per-stream frame rate (FPS) for
            the specified pipelines with given number of streams
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
                      onValueChange={(value) =>
                        handleVariantChange(index, value)
                      }
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
                      Streams
                    </label>
                    <StreamsSlider
                      value={selection.streams}
                      onChange={(val) => handleStreamsChange(index, val)}
                      min={1}
                      max={64}
                    />
                  </div>
                </div>

                {pipelineSelections.length > 1 && (
                  <Button
                    onClick={() => handleRemovePipeline(selection.pipelineId)}
                    variant="ghost"
                    size="icon"
                    className="text-destructive"
                  >
                    <X className="w-5 h-5" />
                  </Button>
                )}
              </div>
            );
          })}

          <Button onClick={handleAddPipeline} variant="outline">
            <Plus className="w-5 h-5" />
            <span>Add Pipeline</span>
          </Button>
        </div>

        <div className="my-4 flex flex-col">
          <div className="flex items-center">
            <Tooltip>
              <TooltipTrigger asChild>
                <label className="flex items-center gap-2 cursor-pointer h-[42px]">
                  <Checkbox
                    checked={videoOutputEnabled}
                    onCheckedChange={(checked) =>
                      setVideoOutputEnabled(checked === true)
                    }
                  />
                  <span className="text-sm font-medium">Save output</span>
                </label>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p>
                  Selecting this option changes the last fakesink to filesink so
                  it is possible to view generated output
                </p>
              </TooltipContent>
            </Tooltip>
          </div>
          {videoOutputEnabled && <SaveOutputWarning />}
        </div>

        <Button
          onClick={handleRunTest}
          disabled={isLoading || pipelineSelections.length === 0}
        >
          {isLoading ? "Running..." : "Run performance test"}
        </Button>

        {jobStatus && (
          <div className="my-4 p-3 bg-classic-blue/5 dark:bg-teal-chart border border-blue-200 dark:border-classic-blue">
            <p className="text-sm font-medium text-blue-900 dark:text-blue-100">
              Test Status: {jobStatus.state}
            </p>
            {jobStatus.state === "RUNNING" && (
              <div className="mt-2">
                <div className="animate-pulse flex items-center gap-2">
                  <div className="h-2 w-2 bg-magenta-chart"></div>
                  <span className="text-xs text-magenta-chart dark:text-magenta-chart">
                    Running performance test...
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
                <span className="font-medium">Total FPS:</span>{" "}
                {testResult.total_fps?.toFixed(2) ?? "N/A"}
              </p>
              <p className="text-green-800 dark:text-green-200">
                <span className="font-medium">Per Stream FPS:</span>{" "}
                {testResult.per_stream_fps?.toFixed(2) ?? "N/A"}
              </p>
            </div>

            {videoOutputEnabled &&
              testResult.video_output_paths &&
              Object.keys(testResult.video_output_paths).length > 0 && (
                <div className="mt-4">
                  <p className="text-sm font-medium text-green-900 dark:text-green-100 mb-3">
                    Output Videos:
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {Object.entries(testResult.video_output_paths).map(
                      ([pipelineId, paths]) => {
                        const videoPath =
                          paths && paths.length > 0 ? [...paths].pop() : null;

                        return (
                          <div
                            key={pipelineId}
                            className="border border-green-300 dark:border-green-700 overflow-hidden"
                          >
                            <div className="bg-green-100 dark:bg-green-900 px-3 py-2">
                              <p className="text-xs font-medium text-green-900 dark:text-green-100">
                                <PipelineName pipelineId={pipelineId} />
                              </p>
                            </div>
                            {videoPath ? (
                              <video
                                controls
                                className="w-full"
                                src={`/assets${videoPath}`}
                              >
                                Your browser does not support the video tag.
                              </video>
                            ) : (
                              <div className="p-4 text-center text-sm text-green-700 dark:text-green-300">
                                no streams
                              </div>
                            )}
                          </div>
                        );
                      },
                    )}
                  </div>
                </div>
              )}
          </div>
        )}
      </div>
    </>
  );
};
