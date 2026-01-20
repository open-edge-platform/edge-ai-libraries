import { useEffect, useState } from "react";
import {
  type PipelinePerformanceSpec,
  useGetDensityJobStatusQuery,
  useRunDensityTestMutation,
} from "@/api/api.generated.ts";
import { PipelineName } from "@/features/pipelines/PipelineName.tsx";
import { MetricChart } from "@/features/metrics/MetricChart";
import { useMetricHistory } from "@/hooks/useMetricHistory.ts";
import { useAppSelector } from "@/store/hooks";
import { selectPipelines } from "@/store/reducers/pipelines";
import { Checkbox } from "@/components/ui/checkbox";
import { Home, ChevronDown } from "lucide-react";
import { ParticipationSlider } from "@/features/pipeline-tests/ParticipationSlider.tsx";
import SaveOutputWarning from "@/features/pipeline-tests/SaveOutputWarning.tsx";
import { useNavigate } from "react-router";
import { usePipelinesLoader } from "@/hooks/usePipelines.ts";
import { useModelsLoader } from "@/hooks/useModels.ts";
import { useDevicesLoader } from "@/hooks/useDevices.ts";
import { Toaster } from "@/components/ui/sonner.tsx";
import { BubbleBackground } from "@/components/ui/shadcn-io/bubble-background";

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
  const [testStarted, setTestStarted] = useState(false);
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

    setTestStarted(true);
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
    <div className="relative h-screen overflow-hidden text-white">
      {/* Animated background */}
      <BubbleBackground interactive={true} className="absolute inset-0 z-0" />

      {/* CONTENT */}
      <div className="relative z-10 h-full bg-slate-950/80">
        {/* HEADER */}
        <div className="h-[70px] px-4 flex items-center justify-between border-b border-cyan-500/30 backdrop-blur-md shadow-lg shadow-cyan-500/10">
          <h1 className="text-3xl font-black bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-400 bg-clip-text text-transparent drop-shadow-[0_0_15px_rgba(34,211,238,0.3)]">
            ViPPET Demo
          </h1>
          <button
            onClick={() => navigate("/")}
            className="group relative px-4 py-2 rounded-xl border border-cyan-500/50 bg-slate-800/50 backdrop-blur-xl hover:bg-cyan-500/20 hover:border-cyan-400 hover:shadow-lg hover:shadow-cyan-500/20 transition-all duration-300"
          >
            <div className="flex items-center gap-2">
              <Home className="w-4 h-4 text-cyan-400 group-hover:scale-110 transition-transform" />
              <span className="text-sm font-semibold text-cyan-400">Exit</span>
            </div>
          </button>
        </div>

        {/* MAIN CONTENT */}
        <div className="relative z-10 h-[calc(100vh-70px)] p-3">
          {!testStarted ? (
            /* CENTERED INITIAL VIEW */
            <div className="h-full flex items-center justify-center gap-6 animate-[fadeIn_0.6s_ease-out]">
              {/* Configuration - Larger */}
              <div className="w-[450px] h-[400px] rounded-2xl bg-gradient-to-br from-slate-900/90 via-slate-800/70 to-slate-900/90 border border-cyan-500/40 p-6 space-y-4 overflow-y-auto backdrop-blur-md shadow-2xl shadow-cyan-500/20 animate-[slideInLeft_0.8s_ease-out]">
                <p className="text-sm uppercase text-cyan-400 font-bold tracking-wider drop-shadow-[0_0_12px_rgba(34,211,238,0.4)] text-center">
                  Configuration
                </p>
                {pipelineSelections.map((selection) => (
                  <div key={selection.pipelineId} className="space-y-4">
                    {/* Model Dropdown */}
                    <div className="space-y-2 relative z-30">
                      <label className="block text-xs font-semibold text-cyan-300/90 uppercase tracking-wider">
                        Model
                      </label>
                      <div className="relative">
                        <button
                          onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                          className="w-full px-4 py-3 bg-slate-950/90 border border-cyan-500/60 rounded-xl text-white text-base text-left flex items-center justify-between hover:border-cyan-400 hover:shadow-lg hover:shadow-cyan-500/30 focus:outline-none focus:ring-2 focus:ring-cyan-400/50 focus:border-cyan-400 transition-all"
                        >
                          <span className="truncate">
                            {currentModel || "Select Model"}
                          </span>
                          <ChevronDown
                            className={`w-5 h-5 text-cyan-400 transition-transform duration-200 flex-shrink-0 ${
                              isDropdownOpen ? "rotate-180" : ""
                            }`}
                          />
                        </button>
                        {isDropdownOpen && (
                          <div className="absolute z-[100] w-full mt-2 bg-slate-900/95 border border-cyan-500/50 rounded-xl shadow-2xl overflow-hidden max-h-64 overflow-y-auto backdrop-blur-md">
                            {uniqueModels.map((model) => (
                              <button
                                key={model}
                                onClick={() => {
                                  handleModelChange(model);
                                  setIsDropdownOpen(false);
                                }}
                                className={`w-full px-4 py-3 text-left text-sm hover:bg-cyan-500/20 transition-colors ${
                                  model === currentModel
                                    ? "bg-cyan-500/30 text-white font-semibold"
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

                    {/* Device Dropdown */}
                    <div className="space-y-2 relative z-20">
                      <label className="block text-xs font-semibold text-cyan-300/90 uppercase tracking-wider">
                        Device
                      </label>
                      <div className="relative">
                        <button
                          onClick={() =>
                            setIsDeviceDropdownOpen(!isDeviceDropdownOpen)
                          }
                          className="w-full px-4 py-3 bg-slate-950/90 border border-cyan-500/60 rounded-xl text-white text-base text-left flex items-center justify-between hover:border-cyan-400 hover:shadow-lg hover:shadow-cyan-500/30 focus:outline-none focus:ring-2 focus:ring-cyan-400/50 focus:border-cyan-400 transition-all"
                        >
                          <span>{currentDevice || "Select Device"}</span>
                          <ChevronDown
                            className={`w-5 h-5 text-cyan-400 transition-transform duration-200 ${
                              isDeviceDropdownOpen ? "rotate-180" : ""
                            }`}
                          />
                        </button>
                        {isDeviceDropdownOpen && (
                          <div className="absolute z-[100] w-full mt-2 bg-slate-900/95 border border-cyan-500/50 rounded-xl shadow-2xl overflow-hidden backdrop-blur-md">
                            {availableDevices.map((item) => (
                              <button
                                key={item.pipelineId}
                                onClick={() => {
                                  handleDeviceChange(item.pipelineId);
                                  setIsDeviceDropdownOpen(false);
                                }}
                                className={`w-full px-4 py-3 text-left text-sm hover:bg-cyan-500/20 transition-colors ${
                                  item.pipelineId === selection.pipelineId
                                    ? "bg-cyan-500/30 text-white font-semibold"
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

                    {/* Participation Rate */}
                    <div className="space-y-2">
                      <label className="block text-xs font-semibold text-cyan-300/90 uppercase tracking-wider">
                        Participation Rate
                      </label>
                      <div className="bg-slate-950/60 rounded-xl p-3 border border-cyan-500/40">
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
                ))}
              </div>

              {/* Test - Larger */}
              <div className="w-[450px] h-[400px] bg-gradient-to-br from-slate-900/90 via-slate-800/70 to-slate-900/90 rounded-2xl p-6 border border-purple-500/40 backdrop-blur-md shadow-2xl shadow-purple-500/20 flex flex-col animate-[slideInRight_0.8s_ease-out]">
                <div className="flex-1 overflow-y-auto space-y-4">
                  <p className="text-sm uppercase text-purple-400 font-bold tracking-wider drop-shadow-[0_0_12px_rgba(168,85,247,0.4)] text-center">
                    Test Configuration
                  </p>

                  {/* FPS Floor */}
                  <div className="space-y-2">
                    <label className="block text-xs font-semibold text-purple-300/90 uppercase tracking-wider">
                      Target FPS
                    </label>
                    <div className="flex items-center gap-3">
                      <input
                        type="number"
                        value={fpsFloor}
                        onChange={(e) => setFpsFloor(Number(e.target.value))}
                        min={1}
                        max={120}
                        className="w-28 px-3 py-3 bg-slate-950/90 border border-purple-500/60 rounded-xl text-white text-lg font-bold focus:outline-none focus:ring-2 focus:ring-purple-400/50 focus:border-purple-400 transition-all shadow-lg shadow-purple-500/20 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                      />
                      <span className="text-purple-300/90 text-base font-semibold">
                        FPS
                      </span>
                    </div>
                  </div>

                  {/* Video Output */}
                  <div>
                    <label className="flex items-center gap-3 cursor-pointer group">
                      <Checkbox
                        checked={videoOutputEnabled}
                        onCheckedChange={(checked) =>
                          setVideoOutputEnabled(checked === true)
                        }
                        className="w-5 h-5 border-purple-400/60 data-[state=checked]:bg-purple-500 data-[state=checked]:border-purple-400"
                      />
                      <span className="text-sm font-semibold text-purple-300/90 group-hover:text-purple-200 transition-colors uppercase tracking-wider">
                        Save Output
                      </span>
                    </label>
                    {videoOutputEnabled && <SaveOutputWarning />}
                  </div>
                </div>

                {/* Run Button - Larger */}
                <button
                  onClick={handleRunTest}
                  disabled={
                    isRunning || pipelineSelections.length === 0 || !!jobId
                  }
                  className="relative w-full px-6 py-5 mt-4 bg-gradient-to-r from-purple-600 via-blue-600 to-cyan-600 hover:from-purple-500 hover:via-blue-500 hover:to-cyan-500 text-white rounded-2xl font-bold text-xl shadow-2xl shadow-purple-500/60 hover:shadow-cyan-500/60 disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none transition-all duration-300 transform hover:scale-[1.03] active:scale-[0.98] border border-purple-400/40 overflow-hidden group"
                >
                  <div className="absolute inset-0 bg-gradient-to-r from-cyan-400/20 via-blue-400/20 to-purple-400/20 opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-xl"></div>
                  <span className="relative drop-shadow-[0_0_12px_rgba(255,255,255,0.4)]">
                    {jobId
                      ? "RUNNING"
                      : isRunning
                        ? "STARTING..."
                        : "START TEST"}
                  </span>
                </button>
              </div>
            </div>
          ) : (
            /* GRID VIEW AFTER TEST STARTS */
            <div className="grid grid-cols-[340px_360px_1fr] grid-rows-[auto_1fr] gap-3 h-full animate-[gridAppear_0.6s_ease-out]">
              {/* TOP LEFT - Configuration */}
              <div className="rounded-xl bg-gradient-to-br from-slate-900/80 via-slate-800/60 to-slate-900/80 border border-cyan-500/30 p-3 space-y-3 overflow-y-auto backdrop-blur-sm shadow-lg shadow-cyan-500/10 animate-[slideToPosition_0.8s_ease-out]">
                <p className="text-[10px] uppercase text-cyan-400 font-bold tracking-wider drop-shadow-[0_0_8px_rgba(34,211,238,0.3)]">
                  Configuration
                </p>

                {pipelineSelections.map((selection) => (
                  <div key={selection.pipelineId} className="space-y-3">
                    {/* Model Dropdown */}
                    <div className="space-y-1.5 relative z-30">
                      <label className="block text-[10px] font-semibold text-cyan-300/80 uppercase tracking-wider">
                        Model
                      </label>
                      <div className="relative">
                        <button
                          onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                          className="w-full px-3 py-2 bg-slate-950/80 border border-cyan-500/50 rounded-lg text-white text-sm text-left flex items-center justify-between hover:border-cyan-400 hover:shadow-lg hover:shadow-cyan-500/20 focus:outline-none focus:ring-2 focus:ring-cyan-400/50 focus:border-cyan-400 transition-all"
                        >
                          <span className="truncate text-xs">
                            {currentModel || "Select Model"}
                          </span>
                          <ChevronDown
                            className={`w-4 h-4 text-neutral-400 transition-transform duration-200 flex-shrink-0 ${
                              isDropdownOpen ? "rotate-180" : ""
                            }`}
                          />
                        </button>
                        {isDropdownOpen && (
                          <div className="absolute z-[100] w-full mt-1 bg-neutral-900 border border-neutral-700 rounded-lg shadow-2xl overflow-hidden max-h-48 overflow-y-auto">
                            {uniqueModels.map((model) => (
                              <button
                                key={model}
                                onClick={() => {
                                  handleModelChange(model);
                                  setIsDropdownOpen(false);
                                }}
                                className={`w-full px-3 py-2 text-left text-xs hover:bg-neutral-800 transition-colors ${
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

                    {/* Device Dropdown */}
                    <div className="space-y-1.5 relative z-20">
                      <label className="block text-[10px] font-semibold text-cyan-300/80 uppercase tracking-wider">
                        Device
                      </label>
                      <div className="relative">
                        <button
                          onClick={() =>
                            setIsDeviceDropdownOpen(!isDeviceDropdownOpen)
                          }
                          className="w-full px-3 py-2 bg-slate-950/80 border border-cyan-500/50 rounded-lg text-white text-sm text-left flex items-center justify-between hover:border-cyan-400 hover:shadow-lg hover:shadow-cyan-500/20 focus:outline-none focus:ring-2 focus:ring-cyan-400/50 focus:border-cyan-400 transition-all"
                        >
                          <span className="text-xs">
                            {currentDevice || "Select Device"}
                          </span>
                          <ChevronDown
                            className={`w-4 h-4 text-neutral-400 transition-transform duration-200 ${
                              isDeviceDropdownOpen ? "rotate-180" : ""
                            }`}
                          />
                        </button>
                        {isDeviceDropdownOpen && (
                          <div className="absolute z-[100] w-full mt-1 bg-neutral-900 border border-neutral-700 rounded-lg shadow-2xl overflow-hidden">
                            {availableDevices.map((item) => (
                              <button
                                key={item.pipelineId}
                                onClick={() => {
                                  handleDeviceChange(item.pipelineId);
                                  setIsDeviceDropdownOpen(false);
                                }}
                                className={`w-full px-3 py-2 text-left text-xs hover:bg-neutral-800 transition-colors ${
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

                    {/* Participation Rate */}
                    <div className="space-y-1.5">
                      <label className="block text-[10px] font-semibold text-cyan-300/80 uppercase tracking-wider">
                        Participation Rate
                      </label>
                      <div className="bg-slate-950/50 rounded-lg p-2 border border-cyan-500/30">
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
                ))}
              </div>

              {/* TOP CENTER - Test Controls */}
              <div className="bg-gradient-to-br from-slate-900/80 via-slate-800/60 to-slate-900/80 rounded-xl p-3 border border-purple-500/30 backdrop-blur-sm shadow-lg shadow-purple-500/10 flex flex-col">
                <div className="flex-1 overflow-y-auto space-y-2.5">
                  <p className="text-[10px] uppercase text-purple-400 font-bold tracking-wider drop-shadow-[0_0_8px_rgba(168,85,247,0.3)]">
                    Test
                  </p>

                  {/* FPS Floor */}
                  <div className="space-y-1.5">
                    <label className="block text-[10px] font-semibold text-purple-300/80 uppercase tracking-wider">
                      Target FPS
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        value={fpsFloor}
                        onChange={(e) => setFpsFloor(Number(e.target.value))}
                        min={1}
                        max={120}
                        className="w-20 px-2 py-1.5 bg-slate-950/80 border border-purple-500/50 rounded-lg text-white text-sm font-bold focus:outline-none focus:ring-2 focus:ring-purple-400/50 focus:border-purple-400 transition-all shadow-lg shadow-purple-500/10 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                      />
                      <span className="text-purple-300/80 text-xs font-semibold">
                        FPS
                      </span>
                    </div>
                  </div>

                  {/* Video Output */}
                  <div>
                    <label className="flex items-center gap-2 cursor-pointer group">
                      <Checkbox
                        checked={videoOutputEnabled}
                        onCheckedChange={(checked) =>
                          setVideoOutputEnabled(checked === true)
                        }
                        className="w-4 h-4 border-neutral-600 data-[state=checked]:bg-white data-[state=checked]:border-white"
                      />
                      <span className="text-[10px] font-semibold text-purple-300/80 group-hover:text-purple-200 transition-colors uppercase tracking-wider">
                        Save Output
                      </span>
                    </label>
                    {videoOutputEnabled && <SaveOutputWarning />}
                  </div>
                </div>

                {/* Run Button */}
                <button
                  onClick={handleRunTest}
                  disabled={
                    isRunning || pipelineSelections.length === 0 || !!jobId
                  }
                  className="relative w-full px-4 py-3 mt-2.5 bg-gradient-to-r from-purple-600 via-blue-600 to-cyan-600 hover:from-purple-500 hover:via-blue-500 hover:to-cyan-500 text-white rounded-xl font-bold text-base shadow-lg shadow-purple-500/50 hover:shadow-cyan-500/50 disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none transition-all duration-300 transform hover:scale-[1.02] active:scale-[0.98] border border-purple-400/30 overflow-hidden group"
                >
                  <div className="absolute inset-0 bg-gradient-to-r from-cyan-400/20 via-blue-400/20 to-purple-400/20 opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-xl"></div>
                  <span className="relative drop-shadow-[0_0_8px_rgba(255,255,255,0.3)]">
                    {jobId ? "RUNNING" : isRunning ? "STARTING..." : "RUN TEST"}
                  </span>
                </button>
              </div>

              {/* RIGHT COLUMN - Results (spans both rows) */}
              <div className="row-span-2 bg-gradient-to-br from-slate-900/80 via-slate-800/60 to-slate-900/80 rounded-xl p-3 border border-blue-500/30 flex flex-col min-h-0 overflow-y-auto w-full backdrop-blur-sm shadow-lg shadow-blue-500/10 animate-[slideUp_0.8s_ease-out_0.3s_both]">
                <p className="text-[10px] uppercase text-blue-400 font-bold tracking-wider mb-2 drop-shadow-[0_0_8px_rgba(59,130,246,0.3)]">
                  Results
                </p>

                {jobId && jobStatus?.state === "RUNNING" && (
                  <div className="mb-3 flex items-center gap-2">
                    <div className="flex gap-1">
                      <div className="h-2 w-2 bg-energy-blue rounded-full animate-bounce"></div>
                      <div
                        className="h-2 w-2 bg-energy-blue rounded-full animate-bounce"
                        style={{ animationDelay: "0.1s" }}
                      ></div>
                      <div
                        className="h-2 w-2 bg-energy-blue rounded-full animate-bounce"
                        style={{ animationDelay: "0.2s" }}
                      ></div>
                    </div>
                    <span className="text-neutral-300 text-xs">
                      Running test...
                    </span>
                  </div>
                )}

                {errorMessage && (
                  <div className="rounded-lg border border-neutral-800 bg-neutral-950/60 p-3 mb-3">
                    <p className="text-sm font-bold text-white mb-1">
                      Test Failed
                    </p>
                    <p className="text-xs text-neutral-300">{errorMessage}</p>
                  </div>
                )}

                {/* Show live metrics during test or completed results */}
                {(jobId || testResult) && (
                  <div className="space-y-3">
                    {/* Summary Stats - tylko po zakończeniu */}
                    {testResult && (
                      <div className="grid grid-cols-2 gap-2">
                        <div className="bg-neutral-950/50 rounded-lg p-2.5 border border-energy-blue/40 relative overflow-hidden">
                          <div className="absolute inset-0 bg-gradient-to-r from-energy-blue/10 via-classic-blue/10 to-energy-blue/10 animate-[pulse_4s_ease-in-out_infinite]"></div>
                          <div className="relative text-center">
                            <p className="text-[9px] text-energy-blue font-semibold uppercase tracking-wider mb-0.5">
                              Per Stream FPS
                            </p>
                            <p className="text-xl font-bold text-energy-blue">
                              {testResult.per_stream_fps?.toFixed(2) ?? "N/A"}
                            </p>
                          </div>
                        </div>
                        <div className="bg-neutral-950/50 rounded-lg p-2.5 border border-green-chart/30 relative overflow-hidden">
                          <div className="absolute inset-0 bg-gradient-to-r from-green-chart/10 via-cyan-400/10 to-magenta-chart/10 animate-[pulse_4s_ease-in-out_infinite]"></div>
                          <div className="relative text-center">
                            <p className="text-[9px] text-green-chart font-semibold uppercase tracking-wider mb-0.5">
                              Total Streams
                            </p>
                            <p className="text-2xl font-bold text-green-chart">
                              {testResult.total_streams ?? "N/A"}
                            </p>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Metric Charts - na żywo podczas testu i po zakończeniu */}
                    {((jobId && history.length > 0) ||
                      metricHistorySnapshot.length > 0) && (
                      <div className="grid grid-cols-2 gap-1.5 w-full">
                        <MetricChart
                          title="FPS"
                          data={(jobId ? history : metricHistorySnapshot).map(
                            (point) => ({
                              timestamp: point.timestamp,
                              value: point.fps ?? 0,
                            }),
                          )}
                          dataKeys={["value"]}
                          colors={["var(--color-magenta-chart)"]}
                          unit=" fps"
                          yAxisDomain={[
                            0,
                            Math.max(
                              ...(jobId ? history : metricHistorySnapshot).map(
                                (d) => d.fps ?? 0,
                              ),
                              60,
                            ),
                          ]}
                          showLegend={false}
                          labels={["FPS"]}
                          className="!h-[135px] w-full"
                        />

                        <MetricChart
                          title="CPU"
                          data={(jobId ? history : metricHistorySnapshot).map(
                            (point) => ({
                              timestamp: point.timestamp,
                              user: point.cpuUser ?? 0,
                            }),
                          )}
                          dataKeys={["user"]}
                          colors={["var(--color-green-chart)"]}
                          unit="%"
                          yAxisDomain={[0, 100]}
                          showLegend={false}
                          labels={["CPU"]}
                          className="!h-[135px] w-full"
                        />

                        <MetricChart
                          title="GPU"
                          data={(jobId ? history : metricHistorySnapshot).map(
                            (point) => {
                              const gpu = point.gpus["0"];
                              return {
                                timestamp: point.timestamp,
                                compute: gpu?.compute ?? 0,
                              };
                            },
                          )}
                          dataKeys={["compute"]}
                          colors={["var(--color-yellow-chart)"]}
                          unit="%"
                          yAxisDomain={[0, 100]}
                          showLegend={false}
                          labels={["GPU"]}
                          className="!h-[135px] w-full"
                        />

                        <MetricChart
                          title="Memory"
                          data={(jobId ? history : metricHistorySnapshot).map(
                            (point) => ({
                              timestamp: point.timestamp,
                              memory: point.memory ?? 0,
                            }),
                          )}
                          dataKeys={["memory"]}
                          colors={["var(--color-cyan-chart)"]}
                          unit="%"
                          yAxisDomain={[0, 100]}
                          showLegend={false}
                          labels={["Memory"]}
                          className="!h-[135px] w-full"
                        />

                        <MetricChart
                          title="CPU Temp"
                          data={(jobId ? history : metricHistorySnapshot).map(
                            (point) => ({
                              timestamp: point.timestamp,
                              temp: point.cpuTemp ?? 0,
                            }),
                          )}
                          dataKeys={["temp"]}
                          colors={["var(--color-red-chart)"]}
                          unit="°C"
                          yAxisDomain={[
                            0,
                            Math.max(
                              ...(jobId ? history : metricHistorySnapshot).map(
                                (d) => d.cpuTemp ?? 0,
                              ),
                              100,
                            ),
                          ]}
                          showLegend={false}
                          labels={["Temp"]}
                          className="!h-[135px] w-full"
                        />

                        <MetricChart
                          title="GPU Freq"
                          data={(jobId ? history : metricHistorySnapshot).map(
                            (point) => ({
                              timestamp: point.timestamp,
                              frequency: point.gpus["0"]?.frequency ?? 0,
                            }),
                          )}
                          dataKeys={["frequency"]}
                          colors={["var(--color-yellow-chart)"]}
                          unit=" GHz"
                          yAxisDomain={[
                            0,
                            Math.max(
                              ...(jobId ? history : metricHistorySnapshot).map(
                                (d) => d.gpus["0"]?.frequency ?? 0,
                              ),
                              3,
                            ),
                          ]}
                          showLegend={false}
                          labels={["Freq"]}
                          className="!h-[135px] w-full"
                        />

                        <MetricChart
                          title="CPU Freq"
                          data={(jobId ? history : metricHistorySnapshot).map(
                            (point) => ({
                              timestamp: point.timestamp,
                              frequency: point.cpuAvgFrequency ?? 0,
                            }),
                          )}
                          dataKeys={["frequency"]}
                          colors={["var(--color-green-chart)"]}
                          unit=" GHz"
                          yAxisDomain={[
                            0,
                            Math.max(
                              ...(jobId ? history : metricHistorySnapshot).map(
                                (d) => d.cpuAvgFrequency ?? 0,
                              ),
                              5,
                            ),
                          ]}
                          showLegend={false}
                          labels={["Freq"]}
                          className="!h-[135px] w-full"
                        />

                        <MetricChart
                          title="GPU Power"
                          data={(jobId ? history : metricHistorySnapshot).map(
                            (point) => ({
                              timestamp: point.timestamp,
                              power: point.gpus["0"]?.gpuPower ?? 0,
                            }),
                          )}
                          dataKeys={["power"]}
                          colors={["var(--color-red-chart)"]}
                          unit=" W"
                          yAxisDomain={[
                            0,
                            Math.max(
                              ...(jobId ? history : metricHistorySnapshot).map(
                                (d) => d.gpus["0"]?.gpuPower ?? 0,
                              ),
                              50,
                            ),
                          ]}
                          showLegend={false}
                          labels={["Power"]}
                          className="!h-[135px] w-full"
                        />
                      </div>
                    )}

                    {/* Video Output */}
                    {videoOutputEnabled &&
                      testResult?.video_output_paths &&
                      Object.keys(testResult.video_output_paths).length > 0 && (
                        <div className="mt-2">
                          <p className="text-[10px] text-neutral-400 font-semibold mb-2 uppercase tracking-wider">
                            📹 Output Videos
                          </p>
                          <div className="space-y-2">
                            {Object.entries(testResult.video_output_paths).map(
                              ([pipelineId, paths]) => {
                                const videoPath =
                                  paths && paths.length > 0
                                    ? [...paths].pop()
                                    : null;

                                return (
                                  <div
                                    key={pipelineId}
                                    className="rounded-lg overflow-hidden border border-neutral-800 bg-neutral-950/50"
                                  >
                                    <div className="bg-neutral-900/50 px-2 py-1.5 border-b border-neutral-800/50">
                                      <p className="text-[10px] font-semibold text-neutral-300">
                                        <PipelineName pipelineId={pipelineId} />
                                      </p>
                                    </div>
                                    {videoPath ? (
                                      <video
                                        controls
                                        className="w-full"
                                        src={`/assets${videoPath}`}
                                      >
                                        Your browser does not support the video
                                        tag.
                                      </video>
                                    ) : (
                                      <div className="p-4 text-center text-neutral-400 text-xs">
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

                {!jobId && !testResult && !errorMessage && (
                  <div className="flex-1 flex items-center justify-center text-neutral-500 text-sm">
                    Waiting for results…
                  </div>
                )}
              </div>

              {/* BOTTOM LEFT - Preview (spans 2 columns) */}
              <div className="col-span-2 bg-gradient-to-br from-slate-900/80 via-slate-800/60 to-slate-900/80 rounded-xl p-3 border border-emerald-500/30 flex flex-col min-h-0 backdrop-blur-sm shadow-lg shadow-emerald-500/10 animate-[slideUp_0.8s_ease-out_0.2s_both]">
                <p className="text-[10px] uppercase text-emerald-400 font-bold tracking-wider mb-2 drop-shadow-[0_0_8px_rgba(16,185,129,0.3)]">
                  Preview
                </p>
                <div className="flex-1 bg-black rounded-lg flex items-center justify-center overflow-hidden">
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
                        const msg = document.createElement("span");
                        msg.className = "text-neutral-600 text-xs";
                        msg.textContent = "No preview";
                        parent.appendChild(msg);
                      }
                    }}
                  >
                    Your browser does not support the video tag.
                  </video>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
      <Toaster position="top-center" richColors />
      <style>{`
        @keyframes float {0%,100%{transform:translateY(0);}50%{transform:translateY(-6px);}}
        @keyframes spin {0%{transform:rotate(0deg);}100%{transform:rotate(360deg);}}
        @keyframes spin_reverse {0%{transform:rotate(360deg);}100%{transform:rotate(0deg);}}
        @keyframes fadeIn {from{opacity:0;}to{opacity:1;}}
        @keyframes slideInLeft {from{opacity:0;transform:translateX(-100px);}to{opacity:1;transform:translateX(0);}}
        @keyframes slideInRight {from{opacity:0;transform:translateX(100px);}to{opacity:1;transform:translateX(0);}}
        @keyframes gridAppear {from{opacity:0;}to{opacity:1;}}
        @keyframes slideToPosition {from{opacity:0;transform:scale(1.2);}to{opacity:1;transform:scale(1);}}
        @keyframes slideUp {from{opacity:0;transform:translateY(50px);}to{opacity:1;transform:translateY(0);}}
        @keyframes gradientShift {0%{background-position:0% 50%;}25%{background-position:100% 50%;}50%{background-position:100% 100%;}75%{background-position:0% 100%;}100%{background-position:0% 50%;}background-size:200% 200%;}
      `}</style>
    </div>
  );
};

export default DemoMode;
