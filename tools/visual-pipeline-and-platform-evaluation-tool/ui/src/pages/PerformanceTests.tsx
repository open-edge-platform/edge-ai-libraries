import { useEffect, useState } from "react";
import {
  useGetPerformanceJobStatusQuery,
  useRunPerformanceTestMutation,
} from "@/api/api.generated";
import { TestProgressIndicator } from "@/features/pipeline-tests/TestProgressIndicator.tsx";
import { PipelineName } from "@/features/pipelines/PipelineName.tsx";
import { useAppSelector } from "@/store/hooks";
import { selectPipelines } from "@/store/reducers/pipelines";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Plus, X } from "lucide-react";
import { StreamsSlider } from "@/features/pipeline-tests/StreamsSlider.tsx";
import SaveOutputWarning from "@/features/pipeline-tests/SaveOutputWarning.tsx";

interface PipelineSelection {
  pipelineId: string;
  streams: number;
  isRemoving?: boolean;
  isNew?: boolean;
}

export const PerformanceTests = () => {
  const pipelines = useAppSelector(selectPipelines);
  const [runPerformanceTest, { isLoading: isRunning }] =
    useRunPerformanceTestMutation();
  const [pipelineSelections, setPipelineSelections] = useState<
    PipelineSelection[]
  >([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{
    total_fps: number | null;
    per_stream_fps: number | null;
    video_output_paths: {
      [key: string]: string[];
    } | null;
  } | null>(null);
  const [videoOutputEnabled, setVideoOutputEnabled] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { data: jobStatus } = useGetPerformanceJobStatusQuery(
    { jobId: jobId! },
    {
      skip: !jobId,
      pollingInterval: 1000, // Poll every second
    },
  );

  useEffect(() => {
    if (jobStatus?.state === "COMPLETED") {
      setTestResult({
        total_fps: jobStatus.total_fps,
        per_stream_fps: jobStatus.per_stream_fps,
        video_output_paths: jobStatus.video_output_paths,
      });
      setErrorMessage(null);
      setJobId(null);
    } else if (jobStatus?.state === "ERROR" || jobStatus?.state === "ABORTED") {
      console.error("Test failed:", jobStatus.error_message);
      setErrorMessage(jobStatus.error_message || "Test failed");
      setTestResult(null);
      setJobId(null);
    }
  }, [jobStatus]);

  useEffect(() => {
    if (pipelines.length > 0 && pipelineSelections.length === 0) {
      setPipelineSelections([
        {
          pipelineId: pipelines[0].id,
          streams: 8,
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
      setPipelineSelections((prev) => [
        ...prev,
        {
          pipelineId: availablePipeline.id,
          streams: 8,
          isNew: true,
        },
      ]);
      setTimeout(() => {
        setPipelineSelections((prev) =>
          prev.map((sel) =>
            sel.pipelineId === availablePipeline.id
              ? { ...sel, isNew: false }
              : sel,
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

  const handlePipelineChange = (
    oldPipelineId: string,
    newPipelineId: string,
  ) => {
    setPipelineSelections((prev) =>
      prev.map((sel) =>
        sel.pipelineId === oldPipelineId
          ? { ...sel, pipelineId: newPipelineId }
          : sel,
      ),
    );
  };

  const handleStreamsChange = (pipelineId: string, streams: number) => {
    setPipelineSelections((prev) =>
      prev.map((sel) =>
        sel.pipelineId === pipelineId ? { ...sel, streams } : sel,
      ),
    );
  };

  const handleRunTest = async () => {
    setTestResult(null);
    setErrorMessage(null);
    try {
      const result = await runPerformanceTest({
        performanceTestSpecInput: {
          execution_config: {
            output_mode: videoOutputEnabled ? "file" : "disabled",
            max_runtime: 0,
          },
          pipeline_performance_specs: pipelineSelections.map((selection) => ({
            id: selection.pipelineId,
            streams: selection.streams,
          })),
        },
      }).unwrap();
      setJobId(result.job_id);
    } catch (err) {
      console.error("Failed to run performance test:", err);
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
          {pipelineSelections.map((selection) => (
            <div
              key={selection.pipelineId}
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
                  <select
                    value={selection.pipelineId}
                    onChange={(e) =>
                      handlePipelineChange(selection.pipelineId, e.target.value)
                    }
                    className="w-full px-3 py-2 border text-sm cursor-pointer bg-background"
                  >
                    {pipelines
                      .filter(
                        (pipeline) =>
                          pipeline.id === selection.pipelineId ||
                          !pipelineSelections.some(
                            (sel) => sel.pipelineId === pipeline.id,
                          ),
                      )
                      .map((pipeline) => (
                        <option key={pipeline.id} value={pipeline.id}>
                          {pipeline.name}
                        </option>
                      ))}
                  </select>
                </div>

                <div className="flex-1">
                  <label className="block text-sm font-medium mb-1">
                    Streams
                  </label>
                  <StreamsSlider
                    value={selection.streams}
                    onChange={(val) =>
                      handleStreamsChange(selection.pipelineId, val)
                    }
                    min={1}
                    max={64}
                  />
                </div>
              </div>

              {pipelineSelections.length > 1 && (
                <button
                  onClick={() => handleRemovePipeline(selection.pipelineId)}
                  className="text-red-500 hover:text-red-700 p-2"
                >
                  <X className="w-5 h-5" />
                </button>
              )}
            </div>
          ))}

          <button
            onClick={handleAddPipeline}
            disabled={pipelineSelections.length >= pipelines.length}
            className="w-fit px-4 py-2 bg-background hover:bg-classic-blue dark:hover:bg-energy-blue border-2 border-classic-blue dark:border-energy-blue text-primary dark:text-energy-blue hover:text-white dark:hover:text-[#242528] transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            <Plus className="w-5 h-5" />
            <span>Add Pipeline</span>
          </button>
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

        <button
          onClick={handleRunTest}
          disabled={isRunning || pipelineSelections.length === 0 || !!jobId}
          className="w-fit px-4 py-2 bg-classic-blue font-medium text-primary-foreground hover:bg-classic-blue-hover disabled:opacity-50 disabled:cursor-not-allowed dark:bg-energy-blue dark:hover:bg-energy-blue-tint-1 transition-colors"
        >
          {jobId
            ? "Running..."
            : isRunning
              ? "Starting..."
              : "Run performance test"}
        </button>

        {jobId && jobStatus && (
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
