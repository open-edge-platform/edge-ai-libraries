import { useEffect, useState } from "react";
import {
  type PipelinePerformanceSpec,
  useGetDensityJobStatusQuery,
  useRunDensityTestMutation,
} from "@/api/api.generated.ts";
import { TestProgressIndicator } from "@/features/pipeline-tests/TestProgressIndicator.tsx";
import { PipelineStreamsSummary } from "@/features/pipeline-tests/PipelineStreamsSummary.tsx";
import { PipelineName } from "@/features/pipelines/PipelineName.tsx";
import { MetricChart } from "@/features/metrics/MetricChart";
import { useMetricHistory } from "@/hooks/useMetricHistory.ts";
import { useAppSelector } from "@/store/hooks";
import { selectPipelines } from "@/store/reducers/pipelines";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Home, ChevronDown } from "lucide-react";
import { ParticipationSlider } from "@/features/pipeline-tests/ParticipationSlider.tsx";
import SaveOutputWarning from "@/features/pipeline-tests/SaveOutputWarning.tsx";
import { useNavigate } from "react-router";
import { usePipelinesLoader } from "@/hooks/usePipelines.ts";
import { useModelsLoader } from "@/hooks/useModels.ts";
import { useDevicesLoader } from "@/hooks/useDevices.ts";
import { Toaster } from "@/components/ui/sonner.tsx";

interface PipelineSelection {
  pipelineId: string;
  stream_rate: number;
}

const DemoMode = () => {
  const navigate = useNavigate();
  usePipelinesLoader();
  useModelsLoader();
  useDevicesLoader();
  const pipelines = useAppSelector(selectPipelines);
  const history = useMetricHistory();
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
  const [videoOutputEnabled, setVideoOutputEnabled] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isDeviceDropdownOpen, setIsDeviceDropdownOpen] = useState(false);
  const [metricHistorySnapshot, setMetricHistorySnapshot] = useState<
    typeof history
  >([]);

  // Parse pipeline names to extract model and device
  const parsePipelineName = (name: string) => {
    // Match device in square brackets [CPU], [GPU], [NPU], etc.
    const deviceMatch = name.match(/\[(.*?)\]/);

    if (deviceMatch) {
      const device = deviceMatch[1].toUpperCase();
      const model = name.replace(/\s*\[.*?\]\s*/, "").trim();
      return { model: model, device: device };
    }

    return { model: name, device: "" };
  };

  // Get unique models and devices
  const uniqueModels = Array.from(
    new Set(pipelines.map((p) => parsePipelineName(p.name).model)),
  );

  const getDevicesForModel = (model: string) => {
    return pipelines
      .filter((p) => parsePipelineName(p.name).model === model)
      .map((p) => ({
        device: parsePipelineName(p.name).device,
        pipelineId: p.id,
      }));
  };

  const selectedPipeline = pipelineSelections[0];
  const selectedPipelineData = pipelines.find(
    (p) => p.id === selectedPipeline?.pipelineId,
  );
  const currentModel = selectedPipelineData
    ? parsePipelineName(selectedPipelineData.name).model
    : "";
  const currentDevice = selectedPipelineData
    ? parsePipelineName(selectedPipelineData.name).device
    : "";
  const availableDevices = getDevicesForModel(currentModel);

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
      // Save snapshot of metric history
      setMetricHistorySnapshot([...history]);
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
        },
      ]);
    }
  }, [pipelines, pipelineSelections.length]);

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

  const handleModelChange = (model: string) => {
    const devicesForModel = getDevicesForModel(model);
    if (devicesForModel.length > 0) {
      handlePipelineChange(
        selectedPipeline.pipelineId,
        devicesForModel[0].pipelineId,
      );
    }
  };

  const handleDeviceChange = (pipelineId: string) => {
    handlePipelineChange(selectedPipeline.pipelineId, pipelineId);
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
      const result = await runDensityTest({
        densityTestSpec: {
          video_output: {
            enabled: videoOutputEnabled,
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
      <div className="flex items-center justify-center h-screen">
        <p>Loading pipelines...</p>
      </div>
    );
  }

  return (
    <>
      <div className="min-h-screen bg-black text-white overflow-auto">
        {/* Animated background */}
        <div className="fixed inset-0 overflow-hidden pointer-events-none">
          <div className="absolute inset-0 bg-gradient-to-br from-magenta-chart/10 to-green-chart/10 animate-[pulse_8s_ease-in-out_infinite]"></div>
          <div className="absolute -top-40 -left-40 w-[600px] h-[600px] bg-white/5 rounded-full blur-3xl animate-[spin_60s_linear_infinite]"></div>
          <div className="absolute bottom-[-200px] right-[-200px] w-[700px] h-[700px] bg-white/3 rounded-full blur-3xl animate-[spin_80s_linear_infinite_reverse]"></div>
        </div>

        <div className="relative z-10 container mx-auto py-8 px-6">
          {/* Header */}
          <div className="mb-8 flex items-center justify-between">
            <div className="space-y-2">
              <h1 className="text-6xl font-black text-white/90">ViPPET</h1>
              <p className="text-neutral-400 text-lg">
                density testing platform
              </p>
            </div>
            <button
              onClick={() => navigate("/")}
              className="group relative px-6 py-3 rounded-xl border border-neutral-700 bg-neutral-900/60 backdrop-blur-xl hover:border-neutral-500 transition-all duration-300"
            >
              <div className="flex items-center gap-2">
                <Home className="w-5 h-5 text-neutral-300 group-hover:scale-110 transition-transform" />
                <span className="font-semibold text-neutral-200">Exit</span>
              </div>
            </button>
          </div>

          {/* Pipeline Configuration */}
          <div className="mb-8 relative z-40">
            {pipelineSelections.map((selection) => (
              <div
                key={selection.pipelineId}
                className="relative rounded-2xl border border-neutral-800 bg-neutral-900/60 backdrop-blur-xl p-6 shadow-2xl overflow-visible"
              >
                <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-40 pointer-events-none rounded-2xl" />
                <div className="relative grid grid-cols-1 md:grid-cols-[1.5fr_1fr_1.3fr] gap-6 overflow-visible">
                  <div className="space-y-3 relative z-30">
                    <label className="block text-xs font-semibold text-neutral-400 uppercase tracking-widest">
                      Model
                    </label>
                    <div className="relative">
                      <button
                        onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                        className="w-full px-4 py-3 bg-neutral-950/80 border border-neutral-700 rounded-xl text-white text-left flex items-center justify-between hover:border-neutral-600 focus:outline-none focus:ring-2 focus:ring-white/30 focus:border-transparent transition-all"
                      >
                        <span>{currentModel || "Select Model"}</span>
                        <ChevronDown
                          className={`w-5 h-5 text-neutral-400 transition-transform duration-200 ${
                            isDropdownOpen ? "rotate-180" : ""
                          }`}
                        />
                      </button>
                      {isDropdownOpen && (
                        <div className="absolute z-[100] w-full mt-2 bg-neutral-900 border border-neutral-700 rounded-xl shadow-2xl overflow-hidden max-h-60 overflow-y-auto">
                          {uniqueModels.map((model) => (
                            <button
                              key={model}
                              onClick={() => {
                                handleModelChange(model);
                                setIsDropdownOpen(false);
                              }}
                              className={`w-full px-4 py-3 text-left hover:bg-neutral-800 transition-colors ${
                                model === currentModel
                                  ? "bg-neutral-800 text-white font-semibold"
                                  : "text-neutral-300"
                              }`}
                            >
                              {model}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="space-y-3 relative z-20">
                    <label className="block text-xs font-semibold text-neutral-400 uppercase tracking-widest">
                      Device
                    </label>
                    <div className="relative">
                      <button
                        onClick={() =>
                          setIsDeviceDropdownOpen(!isDeviceDropdownOpen)
                        }
                        className="w-full px-4 py-3 bg-neutral-950/80 border border-neutral-700 rounded-xl text-white text-left flex items-center justify-between hover:border-neutral-600 focus:outline-none focus:ring-2 focus:ring-white/30 focus:border-transparent transition-all"
                      >
                        <span>{currentDevice || "Select Device"}</span>
                        <ChevronDown
                          className={`w-5 h-5 text-neutral-400 transition-transform duration-200 ${
                            isDeviceDropdownOpen ? "rotate-180" : ""
                          }`}
                        />
                      </button>
                      {isDeviceDropdownOpen && (
                        <div className="absolute z-[100] w-full mt-2 bg-neutral-900 border border-neutral-700 rounded-xl shadow-2xl overflow-hidden">
                          {availableDevices.map((item) => (
                            <button
                              key={item.pipelineId}
                              onClick={() => {
                                handleDeviceChange(item.pipelineId);
                                setIsDeviceDropdownOpen(false);
                              }}
                              className={`w-full px-4 py-3 text-left hover:bg-neutral-800 transition-colors ${
                                item.pipelineId === selection.pipelineId
                                  ? "bg-neutral-800 text-white font-semibold"
                                  : "text-neutral-300"
                              }`}
                            >
                              {item.device}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="space-y-3">
                    <label className="block text-xs font-semibold text-neutral-400 uppercase tracking-widest">
                      Participation Rate
                    </label>
                    <div className="bg-neutral-950/50 rounded-xl p-4 border border-neutral-800/50">
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
                </div>
              </div>
            ))}
          </div>

          {/* Test Configuration */}
          <div className="relative rounded-2xl border border-neutral-800 bg-neutral-900/50 backdrop-blur-xl p-6 shadow-2xl mb-8">
            <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-40 pointer-events-none rounded-2xl" />
            <div className="relative space-y-6">
              <div className="space-y-3">
                <label className="block text-xs font-semibold text-neutral-400 uppercase tracking-widest">
                  Target FPS
                </label>
                <div className="flex items-center gap-4">
                  <input
                    type="number"
                    value={fpsFloor}
                    onChange={(e) => setFpsFloor(Number(e.target.value))}
                    min={1}
                    max={120}
                    className="w-32 px-4 py-3 bg-neutral-950/80 border border-neutral-700 rounded-xl text-white text-lg font-bold focus:outline-none focus:ring-2 focus:ring-white/30 focus:border-transparent transition-all [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                  />
                  <span className="text-neutral-400 font-semibold">FPS</span>
                </div>
              </div>

              <div>
                <label className="flex items-center gap-3 cursor-pointer group">
                  <div className="relative">
                    <Checkbox
                      checked={videoOutputEnabled}
                      onCheckedChange={(checked) =>
                        setVideoOutputEnabled(checked === true)
                      }
                      className="w-6 h-6 border-neutral-600 data-[state=checked]:bg-white data-[state=checked]:border-white"
                    />
                  </div>
                  <span className="text-xs font-semibold text-neutral-300 group-hover:text-white transition-colors uppercase tracking-widest">
                    Save Output
                  </span>
                </label>
                {videoOutputEnabled && <SaveOutputWarning />}
              </div>
            </div>

            <div className="relative mt-6">
              <button
                onClick={handleRunTest}
                disabled={
                  isRunning || pipelineSelections.length === 0 || !!jobId
                }
                className="relative w-full px-8 py-4 bg-neutral-900 hover:bg-neutral-950 text-white rounded-xl font-bold text-lg shadow-lg disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none transition-all duration-300 transform hover:scale-[1.02] active:scale-[0.98] border border-neutral-800 overflow-hidden group"
              >
                <div className="absolute inset-0 bg-gradient-to-r from-magenta-chart/10 via-purple-400/10 via-green-chart/10 opacity-50 group-hover:opacity-100 transition-opacity duration-500"></div>
                <span className="relative">
                  {jobId
                    ? "Running Test..."
                    : isRunning
                      ? "Starting..."
                      : "Run Density Test"}
                </span>
              </button>
            </div>
          </div>

          {/* Status Messages */}
          {jobId && jobStatus && (
            <div className="rounded-2xl border border-neutral-800 bg-neutral-900/60 backdrop-blur-xl p-6 shadow-xl mb-8">
              <div className="flex items-center gap-3 mb-4">
                <div className="h-3 w-3 bg-white rounded-full animate-pulse"></div>
                <p className="text-lg font-bold text-white">
                  Test Status: {jobStatus.state}
                </p>
              </div>
              {jobStatus.state === "RUNNING" && (
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="flex gap-1">
                      <div className="h-2 w-2 bg-neutral-400 rounded-full animate-bounce"></div>
                      <div
                        className="h-2 w-2 bg-neutral-400 rounded-full animate-bounce"
                        style={{ animationDelay: "0.1s" }}
                      ></div>
                      <div
                        className="h-2 w-2 bg-neutral-400 rounded-full animate-bounce"
                        style={{ animationDelay: "0.2s" }}
                      ></div>
                    </div>
                    <span className="text-neutral-300">
                      Running density test...
                    </span>
                  </div>

                  {/* Live Video Preview */}
                  <div className="rounded-xl overflow-hidden border border-neutral-800 bg-neutral-950/50 shadow-lg mt-4">
                    <div className="bg-neutral-900/50 px-4 py-3 border-b border-neutral-800/50">
                      <p className="text-sm font-semibold text-neutral-300">
                        Live Preview
                      </p>
                    </div>
                    <div className="aspect-video bg-neutral-900/30 flex items-center justify-center">
                      <video
                        autoPlay
                        muted
                        loop
                        className="w-full h-full object-contain"
                        src="/assets/preview-stream.mp4"
                        onError={(e) => {
                          e.currentTarget.style.display = "none";
                          const parent = e.currentTarget.parentElement;
                          if (parent) {
                            parent.innerHTML =
                              '<div class="flex items-center justify-center h-full"><span class="text-neutral-500 text-sm">No preview available</span></div>';
                          }
                        }}
                      >
                        Your browser does not support the video tag.
                      </video>
                    </div>
                  </div>

                  <TestProgressIndicator />
                </div>
              )}
            </div>
          )}

          {errorMessage && (
            <div className="rounded-2xl border border-neutral-800 bg-neutral-900/60 backdrop-blur-xl p-6 shadow-xl mb-8">
              <p className="text-lg font-bold text-white mb-2">Test Failed</p>
              <p className="text-neutral-300">{errorMessage}</p>
            </div>
          )}

          {testResult && (
            <div className="rounded-2xl border border-neutral-800 bg-neutral-900/60 backdrop-blur-xl p-6 shadow-xl mb-8">
              <p className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                ✓ Test Completed Successfully
              </p>
              <div className="grid grid-cols-1 lg:grid-cols-[350px_1fr] gap-6 mb-6">
                <div className="flex flex-col gap-4">
                  <div className="bg-neutral-950/50 rounded-xl p-4 border border-magenta-chart/30 relative overflow-hidden flex-1">
                    <div className="absolute inset-0 bg-gradient-to-r from-magenta-chart/10 via-purple-400/10 to-green-chart/10 animate-[pulse_4s_ease-in-out_infinite]"></div>
                    <div className="relative h-full flex flex-col justify-center items-center text-center">
                      <p className="text-xs text-magenta-chart font-semibold uppercase tracking-widest mb-1">
                        Per Stream FPS
                      </p>
                      <p className="text-4xl font-bold text-magenta-chart">
                        {testResult.per_stream_fps?.toFixed(2) ?? "N/A"}
                      </p>
                    </div>
                  </div>
                  <div className="bg-neutral-950/50 rounded-xl p-4 border border-green-chart/30 relative overflow-hidden flex-1">
                    <div className="absolute inset-0 bg-gradient-to-r from-green-chart/10 via-cyan-400/10 to-magenta-chart/10 animate-[pulse_4s_ease-in-out_infinite]"></div>
                    <div className="relative h-full flex flex-col justify-center items-center text-center">
                      <p className="text-xs text-green-chart font-semibold uppercase tracking-widest mb-1">
                        Total Streams
                      </p>
                      <p className="text-4xl font-bold text-green-chart">
                        {testResult.total_streams ?? "N/A"}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Video Preview */}
                <div className="rounded-xl overflow-hidden border border-neutral-800 bg-neutral-950/50 shadow-lg">
                  <div className="bg-neutral-900/50 px-4 py-3 border-b border-neutral-800/50">
                    <p className="text-sm font-semibold text-neutral-300">
                      Test Preview
                    </p>
                  </div>
                  <div className="aspect-video bg-neutral-900/30 flex items-center justify-center">
                    <video
                      autoPlay
                      muted
                      loop
                      className="w-full h-full object-contain"
                      src="/assets/preview-stream.mp4"
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                        const parent = e.currentTarget.parentElement;
                        if (parent) {
                          parent.innerHTML =
                            '<div class="flex items-center justify-center h-full"><span class="text-neutral-500 text-sm">No preview available</span></div>';
                        }
                      }}
                    >
                      Your browser does not support the video tag.
                    </video>
                  </div>
                </div>
              </div>

              {/* Metric Charts Summary */}
              {metricHistorySnapshot.length > 0 && (
                <div className="mt-8">
                  <p className="text-neutral-400 font-semibold mb-4 uppercase tracking-widest text-xs">
                    Performance Metrics Summary
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {/* Frame Rate Column */}
                    <MetricChart
                      title="Frame Rate Over Time"
                      data={metricHistorySnapshot.map((point) => ({
                        timestamp: point.timestamp,
                        value: point.fps ?? 0,
                      }))}
                      dataKeys={["value"]}
                      colors={["var(--color-magenta-chart)"]}
                      unit=" fps"
                      yAxisDomain={[
                        0,
                        Math.max(
                          ...metricHistorySnapshot.map((d) => d.fps ?? 0),
                          60,
                        ),
                      ]}
                      showLegend={false}
                      labels={["Frame Rate"]}
                      className="!h-[200px]"
                    />

                    {/* CPU Column */}
                    <MetricChart
                      title="CPU Usage Over Time"
                      data={metricHistorySnapshot.map((point) => ({
                        timestamp: point.timestamp,
                        user: point.cpuUser ?? 0,
                      }))}
                      dataKeys={["user"]}
                      colors={["var(--color-green-chart)"]}
                      unit="%"
                      yAxisDomain={[0, 100]}
                      showLegend={false}
                      labels={["CPU Usage"]}
                      className="!h-[200px]"
                    />

                    {/* GPU Column */}
                    <MetricChart
                      title="GPU Usage Over Time"
                      data={metricHistorySnapshot.map((point) => {
                        const gpu = point.gpus["0"];
                        return {
                          timestamp: point.timestamp,
                          compute: gpu?.compute ?? 0,
                          render: gpu?.render ?? 0,
                          copy: gpu?.copy ?? 0,
                          video: gpu?.video ?? 0,
                          videoEnhance: gpu?.videoEnhance ?? 0,
                        };
                      })}
                      dataKeys={[
                        "compute",
                        "render",
                        "copy",
                        "video",
                        "videoEnhance",
                      ]}
                      colors={[
                        "var(--color-yellow-chart)",
                        "var(--color-orange-chart)",
                        "var(--color-purple-chart)",
                        "var(--color-red-chart)",
                        "var(--color-geode-chart)",
                      ]}
                      unit="%"
                      yAxisDomain={[0, 100]}
                      showLegend={true}
                      labels={[
                        "Compute",
                        "Render",
                        "Copy",
                        "Video",
                        "Video Enhance",
                      ]}
                      className="!h-[200px]"
                    />

                    <MetricChart
                      title="Memory Utilization Over Time"
                      data={metricHistorySnapshot.map((point) => ({
                        timestamp: point.timestamp,
                        memory: point.memory ?? 0,
                      }))}
                      dataKeys={["memory"]}
                      colors={["var(--color-magenta-chart)"]}
                      unit="%"
                      yAxisDomain={[0, 100]}
                      showLegend={false}
                      labels={["Memory"]}
                      className="!h-[200px]"
                    />

                    <MetricChart
                      title="CPU Temperature Over Time"
                      data={metricHistorySnapshot.map((point) => ({
                        timestamp: point.timestamp,
                        temp: point.cpuTemp ?? 0,
                      }))}
                      dataKeys={["temp"]}
                      colors={["var(--color-green-chart)"]}
                      unit="°C"
                      yAxisDomain={[
                        0,
                        Math.max(
                          ...metricHistorySnapshot.map((d) => d.cpuTemp ?? 0),
                          100,
                        ),
                      ]}
                      showLegend={false}
                      labels={["Temperature"]}
                      className="!h-[200px]"
                    />

                    <MetricChart
                      title="GPU Frequency Over Time"
                      data={metricHistorySnapshot.map((point) => ({
                        timestamp: point.timestamp,
                        frequency: point.gpus["0"]?.frequency ?? 0,
                      }))}
                      dataKeys={["frequency"]}
                      colors={["var(--color-yellow-chart)"]}
                      unit=" GHz"
                      yAxisDomain={[
                        0,
                        Math.max(
                          ...metricHistorySnapshot.map(
                            (d) => d.gpus["0"]?.frequency ?? 0,
                          ),
                          3,
                        ),
                      ]}
                      showLegend={false}
                      labels={["Frequency"]}
                      className="!h-[200px]"
                    />

                    <div></div>

                    <MetricChart
                      title="CPU Frequency Over Time"
                      data={metricHistorySnapshot.map((point) => ({
                        timestamp: point.timestamp,
                        frequency: point.cpuAvgFrequency ?? 0,
                      }))}
                      dataKeys={["frequency"]}
                      colors={["var(--color-green-chart)"]}
                      unit=" GHz"
                      yAxisDomain={[
                        0,
                        Math.max(
                          ...metricHistorySnapshot.map(
                            (d) => d.cpuAvgFrequency ?? 0,
                          ),
                          5,
                        ),
                      ]}
                      showLegend={false}
                      labels={["Frequency"]}
                      className="!h-[200px]"
                    />

                    <MetricChart
                      title="GPU Power Usage Over Time"
                      data={metricHistorySnapshot.map((point) => ({
                        timestamp: point.timestamp,
                        gpuPower: point.gpus["0"]?.gpuPower ?? 0,
                        pkgPower: point.gpus["0"]?.pkgPower ?? 0,
                      }))}
                      dataKeys={["gpuPower", "pkgPower"]}
                      colors={[
                        "var(--color-red-chart)",
                        "var(--color-yellow-chart)",
                      ]}
                      unit=" W"
                      yAxisDomain={[
                        0,
                        Math.max(
                          ...metricHistorySnapshot.map((d) =>
                            Math.max(
                              d.gpus["0"]?.gpuPower ?? 0,
                              d.gpus["0"]?.pkgPower ?? 0,
                            ),
                          ),
                          50,
                        ),
                      ]}
                      showLegend={true}
                      labels={["GPU Power", "Package Power"]}
                      className="!h-[200px]"
                    />
                  </div>
                </div>
              )}

              {videoOutputEnabled &&
                testResult.video_output_paths &&
                Object.keys(testResult.video_output_paths).length > 0 && (
                  <div className="mt-6">
                    <p className="text-neutral-400 font-semibold mb-4 uppercase tracking-widest text-xs">
                      📹 Output Videos
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      {Object.entries(testResult.video_output_paths).map(
                        ([pipelineId, paths]) => {
                          const videoPath =
                            paths && paths.length > 0 ? [...paths].pop() : null;

                          return (
                            <div
                              key={pipelineId}
                              className="rounded-xl overflow-hidden border border-neutral-800 bg-neutral-950/50 shadow-lg"
                            >
                              <div className="bg-neutral-900/50 px-4 py-3 border-b border-neutral-800/50">
                                <p className="text-sm font-semibold text-neutral-300">
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
                                <div className="p-8 text-center text-neutral-400">
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
      <Toaster position="top-center" richColors />
      <style>{`
        @keyframes float {0%,100%{transform:translateY(0);}50%{transform:translateY(-6px);}}
        @keyframes spin {0%{transform:rotate(0deg);}100%{transform:rotate(360deg);}}
        @keyframes spin_reverse {0%{transform:rotate(360deg);}100%{transform:rotate(0deg);}}
      `}</style>
    </>
  );
};

export default DemoMode;
