import { useEffect, useState } from "react";
import {
  useGetPerformanceJobStatusQuery,
  useGetPipelinesQuery,
  useRunPerformanceTestMutation,
} from "@/api/api.generated";
import {
  PipelinesDataTable,
  type PipelineWithStreams,
} from "@/components/shared/PipelinesDataTable";
import { TestProgressIndicator } from "@/components/shared/TestProgressIndicator.tsx";

const PerformanceTests = () => {
  const { data: pipelines, isLoading, error } = useGetPipelinesQuery();
  const [runPerformanceTest, { isLoading: isRunning }] =
    useRunPerformanceTestMutation();
  const [selectedPipelines, setSelectedPipelines] = useState<
    PipelineWithStreams[]
  >([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{
    total_fps: number | null;
    per_stream_fps: number | null;
    video_output_paths: {
      [key: string]: string[];
    } | null;
  } | null>(null);
  const [videoOutputEnabled, setVideoOutputEnabled] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [encoderDevice, setEncoderDevice] = useState<string>("CPU");

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

  const handleRunTest = async () => {
    if (selectedPipelines.length === 0) return;

    setTestResult(null);
    setErrorMessage(null);
    try {
      const result = await runPerformanceTest({
        performanceTestSpecInput: {
          video_output: {
            enabled: videoOutputEnabled,
            encoder_device: videoOutputEnabled
              ? {
                  device_name: encoderDevice.startsWith("GPU") ? "GPU" : "CPU",
                  gpu_id: encoderDevice.startsWith("GPU")
                    ? parseInt(encoderDevice.split("/")[1])
                    : undefined,
                }
              : undefined,
          },
          pipeline_performance_specs: selectedPipelines.map((pipeline) => ({
            id: pipeline.id,
            streams: pipeline.streams,
          })),
        },
      }).unwrap();
      setJobId(result.job_id);
    } catch (err) {
      console.error("Failed to run performance test:", err);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <p>Loading pipelines...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-red-500">Error loading pipelines</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <div className="container mx-auto py-10">
        <div className="mb-6">
          <h1 className="text-3xl font-bold">Performance Tests</h1>
          <p className="text-muted-foreground mt-2">
            Select pipelines to run performance tests on
          </p>
        </div>

        <PipelinesDataTable
          data={pipelines ?? []}
          onSelectionChange={setSelectedPipelines}
        />

        <div className="my-4 flex flex-col gap-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={videoOutputEnabled}
              onChange={(e) => setVideoOutputEnabled(e.target.checked)}
              className="w-4 h-4 cursor-pointer"
            />
            <span className="text-sm font-medium">Create Video</span>
          </label>

          {videoOutputEnabled && (
            <select
              value={encoderDevice}
              onChange={(e) => setEncoderDevice(e.target.value)}
              className="w-fit px-3 py-2 border rounded-md text-sm cursor-pointer"
            >
              <option value="CPU">CPU</option>
              <option value="GPU/0">GPU/0</option>
              <option value="GPU/1">GPU/1</option>
            </select>
          )}

          <button
            onClick={handleRunTest}
            disabled={isRunning || selectedPipelines.length === 0 || !!jobId}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {jobId ? "Running..." : isRunning ? "Starting..." : "Run test"}
          </button>
        </div>

        {jobId && jobStatus && (
          <div className="mb-4 p-3 bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-md">
            <p className="text-sm font-medium text-blue-900 dark:text-blue-100">
              Test Status: {jobStatus.state}
            </p>
            {jobStatus.state === "RUNNING" && (
              <div className="mt-2">
                <div className="animate-pulse flex items-center gap-2">
                  <div className="h-2 w-2 bg-blue-500 rounded-full"></div>
                  <span className="text-xs text-blue-700 dark:text-blue-300">
                    Running performance test...
                  </span>
                </div>
                <TestProgressIndicator />
              </div>
            )}
          </div>
        )}

        {errorMessage && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-md">
            <p className="text-sm font-medium text-red-900 dark:text-red-100 mb-2">
              Test Failed
            </p>
            <p className="text-xs text-red-700 dark:text-red-300">
              {errorMessage}
            </p>
          </div>
        )}

        {testResult && (
          <div className="mb-4 p-3 bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 rounded-md">
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
                        const pipeline = pipelines?.find(
                          (p) => p.id === pipelineId,
                        );
                        const videoPath =
                          paths && paths.length > 0 ? [...paths].pop() : null;

                        return (
                          <div
                            key={pipelineId}
                            className="border border-green-300 dark:border-green-700 rounded-md overflow-hidden"
                          >
                            <div className="bg-green-100 dark:bg-green-900 px-3 py-2">
                              <p className="text-xs font-medium text-green-900 dark:text-green-100">
                                {pipeline?.name || pipelineId}
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
    </div>
  );
};

export default PerformanceTests;
