import { useEffect, useState } from "react";
import {
  type PipelinePerformanceSpec,
  useGetDensityJobStatusQuery,
  useRunDensityTestMutation,
} from "@/api/api.generated.ts";
import { TestProgressIndicator } from "@/components/shared/TestProgressIndicator.tsx";
import { PipelineStreamsSummary } from "@/components/shared/PipelineStreamsSummary.tsx";
import { PipelineName } from "@/components/shared/PipelineName.tsx";
import { useAppSelector } from "@/store/hooks";
import { selectPipelines } from "@/store/reducers/pipelines";
import { selectDevices } from "@/store/reducers/devices";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Plus, X } from "lucide-react";
import { ParticipationSlider } from "@/components/shared/ParticipationSlider";
import DeviceSelect from "@/components/shared/DeviceSelect";

interface PipelineSelection {
  pipelineId: string;
  stream_rate: number;
  isRemoving?: boolean;
  isNew?: boolean;
}

const DensityTests = () => {
  const pipelines = useAppSelector(selectPipelines);
  const devices = useAppSelector(selectDevices);
  const [runDensityTest, { isLoading: isRunning }] =
    useRunDensityTestMutation();
  const [pipelineSelections, setPipelineSelections] = useState<
    PipelineSelection[]
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

  useEffect(() => {
    if (pipelines.length > 0 && pipelineSelections.length === 0) {
      setPipelineSelections([
        {
          pipelineId: pipelines[0].id,
          stream_rate: 50,
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
          stream_rate: 50,
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

  const handleStreamRateChange = (pipelineId: string, stream_rate: number) => {
    setPipelineSelections((prev) =>
      prev.map((sel) =>
        sel.pipelineId === pipelineId ? { ...sel, stream_rate } : sel,
      ),
    );
  };

  const handleRunTest = async () => {
    if (pipelineSelections.length === 0) return;

    setTestResult(null);
    setErrorMessage(null);
    try {
      const selectedDevice = devices.find(
        (d) => d.device_name === encoderDevice,
      );

      const result = await runDensityTest({
        densityTestSpecInput: {
          video_output: {
            enabled: videoOutputEnabled,
            encoder_device:
              videoOutputEnabled && selectedDevice
                ? {
                    device_name: selectedDevice.device_name,
                    gpu_id:
                      selectedDevice.device_family === "GPU"
                        ? (selectedDevice.gpu_id ?? 0)
                        : undefined,
                  }
                : undefined,
          },
          fps_floor: fpsFloor,
          pipeline_density_specs: pipelineSelections.map((selection) => ({
            id: selection.pipelineId,
            stream_rate: selection.stream_rate,
          })),
        },
      }).unwrap();
      setJobId(result.job_id);
    } catch (err) {
      console.error("Failed to run density test:", err);
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
    <div className="h-full overflow-auto">
      <div className="container mx-auto py-10">
        <div className="mb-6">
          <h1 className="text-3xl font-bold">Density Tests</h1>
          <p className="text-muted-foreground mt-2">
            Density test finds the maximum number of streams per pipeline for
            the specified minimum FPS per stream
          </p>
        </div>

        <div className="space-y-3 mb-6">
          {pipelineSelections.map((selection) => (
            <div
              key={selection.pipelineId}
              className={`flex items-center gap-3 p-2 border bg-white transition-all duration-300 ${
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
                    className="w-full px-3 py-2 border text-sm cursor-pointer"
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
                    Participation Rate
                  </label>
                  <ParticipationSlider
                    value={selection.stream_rate}
                    onChange={(val) =>
                      handleStreamRateChange(selection.pipelineId, val)
                    }
                    min={0}
                    max={100}
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
            className="w-fit px-4 py-2 bg-white hover:bg-carbon border border-classic-blue text-primary hover:text-white transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Plus className="w-5 h-5" />
            <span>Add Pipeline</span>
          </button>
        </div>

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
                    Selecting this option changes the last fakesink to filesink
                    so it is possible to view generated output
                  </p>
                </TooltipContent>
              </Tooltip>
            </div>
            {videoOutputEnabled && (
              <div>
                <span>Select device for encoding: </span>
                <DeviceSelect
                  value={encoderDevice}
                  onChange={setEncoderDevice}
                  className="w-fit px-3 py-2 border text-sm cursor-pointer"
                />
              </div>
            )}
            {videoOutputEnabled && (
              <div className="text-muted-foreground">
                Note: Select the device that is used in other blocks in your
                pipeline.
              </div>
            )}
          </div>

          <button
            onClick={handleRunTest}
            disabled={isRunning || pipelineSelections.length === 0 || !!jobId}
            className="w-fit px-4 py-2 bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {jobId
              ? "Running..."
              : isRunning
                ? "Starting..."
                : "Run density test"}
          </button>

          {jobId && jobStatus && (
            <div className="mb-4 p-3 bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800">
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
            <div className="mb-4 p-3 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800">
              <p className="text-sm font-medium text-red-900 dark:text-red-100 mb-2">
                Test Failed
              </p>
              <p className="text-xs text-red-700 dark:text-red-300">
                {errorMessage}
              </p>
            </div>
          )}

          {testResult && (
            <div className="mb-4 p-3 bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800">
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
      </div>
    </div>
  );
};

export default DensityTests;
