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
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Home, ChevronDown, ChevronRight } from "lucide-react";
import pipeline0 from "@/assets/pipeline_0.png";
import pipeline1 from "@/assets/pipeline_1.png";
import pipeline2 from "@/assets/pipeline_2.png";
import pipeline3 from "@/assets/pipeline_3.png";
import pipeline4 from "@/assets/pipeline_4.png";
import pipeline5 from "@/assets/pipeline_5.png";
import type { Pipeline } from "@/api/api.generated";
import { ParticipationSlider } from "@/features/pipeline-tests/ParticipationSlider.tsx";
import SaveOutputWarning from "@/features/pipeline-tests/SaveOutputWarning.tsx";
import { useNavigate } from "react-router";
import { usePipelinesLoader } from "@/hooks/usePipelines.ts";
import { useModelsLoader } from "@/hooks/useModels.ts";
import { useDevicesLoader } from "@/hooks/useDevices.ts";
import { Toaster } from "@/components/ui/sonner.tsx";
import { BubbleBackground } from "@/components/ui/shadcn-io/bubble-background";

const pipelineImages = [
  pipeline0,
  pipeline1,
  pipeline2,
  pipeline3,
  pipeline4,
  pipeline5,
];

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
  const [selectedModels, setSelectedModels] = useState<Map<string, string>>(
    new Map(),
  ); // Map<baseName, selectedPipelineId>
  const [demoStep, setDemoStep] = useState<"selection" | "configuration">(
    "selection",
  );

  const colorModes = {
    first: "180,230,255",
    second: "15,76,129",
    third: "120,190,255",
    fourth: "30,90,150",
    fifth: "200,240,255",
    sixth: "140,210,255",
  };

  // UI color styles
  const colors = {
    headerTitle: "text-blue-500",
    headerGradient: "from-slate-600 via-blue-600 to-blue-500",
    exitButton:
      "border-slate-400/40 hover:bg-blue-600/10 hover:border-blue-500/50",
    exitIcon: "text-blue-500",
    configBorder: "border-slate-400/30 shadow-xl",
    configTitle: "text-blue-600",
    label: "text-slate-400",
    dropdown:
      "border-slate-400/40 hover:border-blue-500/60 focus:ring-blue-500/30 focus:border-blue-500",
    dropdownIcon: "text-slate-400",
    dropdownBg: "bg-slate-900/95 border-slate-400/40",
    dropdownHover: "hover:bg-blue-600/20",
    dropdownActive: "bg-blue-600/30",
    participationBorder: "border-slate-400/30",
    testBorder: "border-slate-400/30 shadow-xl",
    testTitle: "text-slate-300",
    testLabel: "text-slate-400",
    testInput:
      "border-slate-400/40 focus:ring-blue-500/30 focus:border-blue-500",
    testInputText: "text-slate-400",
    checkbox:
      "border-slate-400/60 data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600",
    checkboxLabel: "text-slate-400 group-hover:text-slate-300",
    runButton:
      "bg-[#0F4C81] hover:bg-[#1565A6] rounded-xl shadow-lg shadow-blue-900/40 hover:shadow-blue-700/50",
    runButtonOverlay: "bg-gradient-to-r from-blue-400/10 to-blue-300/10",
    runButtonText: "",
    gridConfigBorder: "border-slate-400/30 shadow-lg",
    gridConfigTitle: "text-slate-300",
    gridTestBorder: "border-slate-400/30 shadow-lg",
    gridTestTitle: "text-slate-300",
    gridResultsBorder: "border-slate-400/30 shadow-lg",
    gridResultsTitle: "text-slate-300",
    gridPreviewBorder: "border-slate-400/30 shadow-lg",
    gridPreviewTitle: "text-slate-300",
    loadingDots: "bg-blue-600",
    summaryFpsBorder: "border-blue-600/40",
    summaryFpsGradient:
      "bg-gradient-to-r from-blue-600/10 via-blue-500/10 to-blue-600/10",
    summaryFpsText: "text-blue-600",
    summaryStreamsBorder: "border-slate-500/30",
    summaryStreamsGradient:
      "bg-gradient-to-r from-slate-600/10 via-slate-500/10 to-slate-600/10",
    summaryStreamsText: "text-slate-400",
    summaryStreamsValueText: "text-slate-300",
  };

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

  // Group pipelines by base name
  const groupedPipelines = pipelines.reduce(
    (acc, pipeline) => {
      const match = pipeline.name.match(/^(.+?)\s*(\[.+?\])?$/);
      const baseName = match ? match[1].trim() : pipeline.name;
      const tag = match && match[2] ? match[2].replace(/[\[\]]/g, "") : null;

      const existing = acc.find((group) => group.baseName === baseName);
      if (existing) {
        if (tag) {
          existing.pipelines[tag] = pipeline;
        }
      } else {
        acc.push({
          baseName,
          pipelines: tag ? { [tag]: pipeline } : {},
          id: pipeline.id,
          description: pipeline.description,
        });
      }
      return acc;
    },
    [] as Array<{
      baseName: string;
      pipelines: Record<string, Pipeline>;
      id: string;
      description: string;
    }>,
  );

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
  }, [jobStatus, history]);

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
      <BubbleBackground
        interactive={true}
        className="absolute inset-0 z-0"
        colors={colorModes}
      />

      {/* CONTENT */}
      <div className="relative z-10 h-full bg-slate-950/80">
        {demoStep === "selection" && (
          /* HEADER - Only for selection step */
          <div className="h-[70px] px-4 flex items-center justify-between border-b border-slate-300/20 backdrop-blur-md shadow-lg">
            <h1 className={`text-xl font-bold ${colors.headerTitle}`}>
              Intel® Visual Pipeline and Platform Evaluation Tool (ViPPET)
            </h1>
            <div className="flex items-center gap-3">
              <button
                onClick={() => navigate("/")}
                className={`group relative px-4 py-2 rounded-lg border bg-slate-800/50 backdrop-blur-xl transition-all duration-300 ${colors.exitButton}`}
              >
                <div className="flex items-center gap-2">
                  <Home
                    className={`w-4 h-4 group-hover:scale-110 transition-transform ${colors.exitIcon}`}
                  />
                  <span className={`text-sm font-semibold ${colors.exitIcon}`}>
                    Exit
                  </span>
                </div>
              </button>
            </div>
          </div>
        )}

        {/* MAIN CONTENT */}
        <div
          className={`relative z-10 p-3 ${demoStep === "selection" ? "h-[calc(100vh-70px)]" : "h-full"}`}
        >
          {demoStep === "selection" ? (
            /* PIPELINE SELECTION VIEW */
            <div className="h-full flex flex-col animate-[fadeIn_0.6s_ease-out]">
              {/* Pipeline Cards Grid */}
              <div className="flex-1 overflow-auto p-6 pt-8">
                <div className="grid gap-6 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {groupedPipelines.map((group, idx) => {
                    const isSelected = selectedModels.has(group.baseName);
                    const availableDevices = Object.keys(group.pipelines);
                    const currentSelectedId = selectedModels.get(
                      group.baseName,
                    );
                    const currentDevice =
                      availableDevices.find(
                        (dev) => group.pipelines[dev].id === currentSelectedId,
                      ) ||
                      availableDevices[0] ||
                      "";

                    return (
                      <Card
                        key={group.id}
                        className={`flex flex-col transition-all duration-300 overflow-hidden border-2 bg-gradient-to-br from-slate-900/90 via-slate-800/70 to-slate-900/90 backdrop-blur-md ${
                          isSelected
                            ? "border-blue-500 shadow-lg shadow-blue-500/50 scale-[1.02]"
                            : "border-slate-400/30 hover:border-blue-500/50 hover:shadow-lg hover:scale-[1.02]"
                        }`}
                      >
                        <CardHeader className="flex-1">
                          <CardTitle className="min-h-8 text-slate-200">
                            {group.baseName}
                          </CardTitle>
                          {pipelineImages[idx % pipelineImages.length] && (
                            <img
                              src={pipelineImages[idx % pipelineImages.length]}
                              alt={group.baseName}
                              className="w-full h-auto rounded-md"
                            />
                          )}
                          <CardDescription className="line-clamp-4 min-h-18 text-slate-400">
                            {group.description}
                          </CardDescription>
                        </CardHeader>
                        <div className="px-6 pb-4 flex items-center gap-3">
                          <Checkbox
                            checked={isSelected}
                            onCheckedChange={(checked) => {
                              const newSelected = new Map(selectedModels);
                              if (checked) {
                                // Select first available device by default
                                const firstDevice = availableDevices[0];
                                if (firstDevice) {
                                  newSelected.set(
                                    group.baseName,
                                    group.pipelines[firstDevice].id,
                                  );
                                }
                              } else {
                                newSelected.delete(group.baseName);
                              }
                              setSelectedModels(newSelected);
                            }}
                            onClick={(e) => e.stopPropagation()}
                            className={`w-5 h-5 ${colors.checkbox}`}
                          />
                          {availableDevices.length > 0 ? (
                            <div className="relative flex-1">
                              <select
                                value={currentDevice}
                                onChange={(e) => {
                                  const newDevice = e.target.value;
                                  const newSelected = new Map(selectedModels);
                                  newSelected.set(
                                    group.baseName,
                                    group.pipelines[newDevice].id,
                                  );
                                  setSelectedModels(newSelected);
                                }}
                                onClick={(e) => e.stopPropagation()}
                                className={`w-full px-3 py-2 bg-slate-950/90 border rounded-lg text-white text-sm focus:outline-none focus:ring-2 transition-all appearance-none cursor-pointer ${colors.dropdown}`}
                                disabled={!isSelected}
                              >
                                {availableDevices.map((device) => (
                                  <option key={device} value={device}>
                                    {device}
                                  </option>
                                ))}
                              </select>
                              <ChevronDown
                                className={`absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 pointer-events-none ${colors.dropdownIcon}`}
                              />
                            </div>
                          ) : (
                            <span className="text-sm text-slate-400">
                              Select pipeline
                            </span>
                          )}
                        </div>
                      </Card>
                    );
                  })}
                </div>
              </div>

              {/* Next Button */}
              <div className="flex justify-end p-3 pt-5">
                <button
                  onClick={() => {
                    if (selectedModels.size > 0) {
                      // Initialize pipeline selections with selected pipelines
                      setPipelineSelections(
                        Array.from(selectedModels.values()).map((id) => ({
                          pipelineId: id,
                          stream_rate: 50,
                        })),
                      );
                      setDemoStep("configuration");
                    }
                  }}
                  disabled={selectedModels.size === 0}
                  className={`group relative px-4 py-2 rounded-lg border bg-slate-800/50 backdrop-blur-xl disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300 ${colors.exitButton}`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-sm font-semibold ${colors.exitIcon}`}
                    >
                      Next
                    </span>
                    <ChevronRight
                      className={`w-4 h-4 group-hover:scale-110 transition-transform ${colors.exitIcon}`}
                    />
                  </div>
                </button>
              </div>
            </div>
          ) : demoStep === "configuration" ? (
            /* 4-PART GRID LAYOUT */
            <div className="grid grid-cols-2 grid-rows-2 gap-4 h-full p-4 animate-[fadeIn_0.6s_ease-out]">
              {/* TOP LEFT - Selected Pipelines Cards */}
              <div className="overflow-y-auto">
                <div className="flex flex-wrap gap-2">
                  {pipelineSelections.map((selection) => {
                    const pipeline = pipelines.find(
                      (p) => p.id === selection.pipelineId,
                    );
                    if (!pipeline) return null;
                    const pipelineIndex = pipelines.findIndex(
                      (p) => p.id === selection.pipelineId,
                    );

                    return (
                      <Card
                        key={selection.pipelineId}
                        className="flex flex-col border border-slate-400/40 bg-gradient-to-br from-slate-800/90 via-slate-750/80 to-slate-800/90 backdrop-blur-md overflow-hidden w-44 shadow-lg hover:shadow-xl transition-shadow"
                      >
                        {pipelineImages[
                          pipelineIndex % pipelineImages.length
                        ] && (
                          <div className="p-2 pb-0">
                            <img
                              src={
                                pipelineImages[
                                  pipelineIndex % pipelineImages.length
                                ]
                              }
                              alt={pipeline.name}
                              className="w-full h-24 object-cover rounded-md"
                            />
                          </div>
                        )}
                        <CardHeader className="p-3 pt-2">
                          <CardTitle className="text-xs text-slate-200 leading-tight text-center font-semibold">
                            {pipeline.name}
                          </CardTitle>
                        </CardHeader>
                      </Card>
                    );
                  })}
                </div>
              </div>

              {/* TOP RIGHT - Preview */}
              <div
                className={`rounded-xl bg-gradient-to-br from-slate-900/90 via-slate-800/70 to-slate-900/90 border p-4 backdrop-blur-md flex flex-col ${colors.gridPreviewBorder}`}
              >
                <p
                  className={`text-sm uppercase font-bold tracking-wider mb-3 ${colors.gridPreviewTitle}`}
                >
                  Preview
                </p>
                <div className="flex-1 flex items-center justify-center text-slate-400">
                  <p className="text-sm">Preview content will appear here</p>
                </div>
              </div>

              {/* BOTTOM LEFT - Pipeline Configuration */}
              <div
                className={`rounded-xl bg-gradient-to-br from-slate-900/90 via-slate-800/70 to-slate-900/90 border p-4 backdrop-blur-md flex flex-col ${colors.testBorder}`}
              >
                <p
                  className={`text-sm uppercase font-bold tracking-wider mb-3 ${colors.testTitle}`}
                >
                  Pipeline Configuration
                </p>
                <div className="flex-1 flex items-center justify-center text-slate-400">
                  <p className="text-sm">
                    Configuration options will appear here
                  </p>
                </div>
              </div>

              {/* BOTTOM RIGHT - Results */}
              <div
                className={`rounded-xl bg-gradient-to-br from-slate-900/90 via-slate-800/70 to-slate-900/90 border p-4 backdrop-blur-md flex flex-col overflow-hidden ${colors.gridResultsBorder}`}
              >
                <p
                  className={`text-sm uppercase font-bold tracking-wider mb-3 ${colors.gridResultsTitle}`}
                >
                  Results
                </p>

                <div className="flex-1 overflow-y-auto">
                  {jobId && jobStatus?.state === "RUNNING" && (
                    <div className="mb-3 flex items-center gap-2">
                      <div className="flex gap-1">
                        <div
                          className={`h-2 w-2 rounded-full animate-bounce ${colors.loadingDots}`}
                        ></div>
                        <div
                          className={`h-2 w-2 rounded-full animate-bounce ${colors.loadingDots}`}
                          style={{ animationDelay: "0.1s" }}
                        ></div>
                        <div
                          className={`h-2 w-2 rounded-full animate-bounce ${colors.loadingDots}`}
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

                  {!testResult && !jobId && !errorMessage && (
                    <div className="flex items-center justify-center h-full text-slate-400">
                      <p className="text-sm">
                        Results will appear here after running the test
                      </p>
                    </div>
                  )}

                  {(jobId || testResult) && (
                    <div className="space-y-3">
                      {testResult && (
                        <div className="grid grid-cols-2 gap-2">
                          <div
                            className={`bg-neutral-950/50 rounded-lg p-2.5 border relative overflow-hidden ${colors.summaryFpsBorder}`}
                          >
                            <div
                              className={`absolute inset-0 animate-[pulse_4s_ease-in-out_infinite] ${colors.summaryFpsGradient}`}
                            ></div>
                            <div className="relative text-center">
                              <p
                                className={`text-[9px] font-semibold uppercase tracking-wider mb-0.5 ${colors.summaryFpsText}`}
                              >
                                Per Stream FPS
                              </p>
                              <p
                                className={`text-xl font-bold ${colors.summaryFpsText}`}
                              >
                                {testResult.per_stream_fps?.toFixed(2) ?? "N/A"}
                              </p>
                            </div>
                          </div>
                          <div
                            className={`bg-neutral-950/50 rounded-lg p-2.5 border relative overflow-hidden ${colors.summaryStreamsBorder}`}
                          >
                            <div
                              className={`absolute inset-0 animate-[pulse_4s_ease-in-out_infinite] ${colors.summaryStreamsGradient}`}
                            ></div>
                            <div className="relative text-center">
                              <p
                                className={`text-[9px] font-semibold uppercase tracking-wider mb-0.5 ${colors.summaryStreamsText}`}
                              >
                                Total Streams
                              </p>
                              <p
                                className={`text-2xl font-bold ${colors.summaryStreamsValueText}`}
                              >
                                {testResult.total_streams ?? "N/A"}
                              </p>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : null}
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
