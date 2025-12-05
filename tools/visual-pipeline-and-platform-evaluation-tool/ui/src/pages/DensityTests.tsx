import { useEffect, useState } from "react";
import {
  type PipelinePerformanceSpec,
  useGetDensityJobStatusQuery,
  useGetPipelinesQuery,
  useRunDensityTestMutation,
} from "@/api/api.generated.ts";
import {
  PipelinesDensityDataTable,
  type PipelineWithParticipation,
} from "@/components/shared/PipelinesDensityDataTable.tsx";
import { TestProgressIndicator } from "@/components/shared/TestProgressIndicator.tsx";
import { PipelineStreamsSummary } from "@/components/shared/PipelineStreamsSummary.tsx";

const DensityTests = () => {
  const { data: pipelines, isLoading, error } = useGetPipelinesQuery();
  const [runDensityTest, { isLoading: isRunning }] =
    useRunDensityTestMutation();
  const [selectedPipelines, setSelectedPipelines] = useState<
    PipelineWithParticipation[]
  >([]);
  const [fpsFloor, setFpsFloor] = useState<number>(30);
  const [jobId, setJobId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{
    per_stream_fps: number | null;
    total_streams: number | null;
    streams_per_pipeline: PipelinePerformanceSpec[] | null;
    video_output_paths: { [key: string]: string[] } | null;
  } | null>(null);
  const [videoOutputEnabled, setVideoOutputEnabled] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [encoderDevice, setEncoderDevice] = useState<string>("CPU");

  const { data: jobStatus } = useGetDensityJobStatusQuery(
    { jobId: jobId! },
    {
      skip: !jobId,
      pollingInterval: 1000,
    },
  );

  useEffect(() => {
    if (jobStatus?.state === "COMPLETED") {
      setTestResult({
        per_stream_fps: jobStatus.per_stream_fps,
        total_streams: jobStatus.total_streams,
        streams_per_pipeline: jobStatus.streams_per_pipeline,
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
      const result = await runDensityTest({
        densityTestSpecInput: {
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
          fps_floor: fpsFloor,
          pipeline_density_specs: selectedPipelines.map((pipeline) => ({
            id: pipeline.id,
            stream_rate: pipeline.stream_rate,
          })),
        },
      }).unwrap();
      setJobId(result.job_id);
    } catch (err) {
      console.error("Failed to run density test:", err);
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
          <h1 className="text-3xl font-bold">Density Tests</h1>
          <p className="text-muted-foreground mt-2">
            Select pipelines and set participation rate for density testing
          </p>
        </div>

        <PipelinesDensityDataTable
          data={pipelines ?? []}
          onSelectionChange={setSelectedPipelines}
        />

        <div className="my-4">
          <label className="block text-sm font-medium mb-2">
            Set target FPS
          </label>
          <div className="flex items-center gap-3">
            <input
              type="number"
              value={fpsFloor}
              onChange={(e) => setFpsFloor(Number(e.target.value))}
              min={1}
              max={120}
              className="w-24 px-3 py-2 border rounded-md"
            />
            <span className="text-sm text-muted-foreground">FPS</span>
          </div>

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
                      Running density test...
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
    </div>
  );
};

export default DensityTests;
