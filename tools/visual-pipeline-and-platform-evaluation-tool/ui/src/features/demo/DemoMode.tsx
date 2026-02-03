import { useEffect, useState } from "react";
import {
  type PipelinePerformanceSpec,
  useGetDensityJobStatusQuery,
  useGetPerformanceJobStatusQuery,
  useRunDensityTestMutation,
  useRunPerformanceTestMutation,
  useUpdatePipelineMutation,
} from "@/api/api.generated.ts";
import { PipelineName } from "@/features/pipelines/PipelineName.tsx";
import { useMetricHistory } from "@/hooks/useMetricHistory.ts";
import { useAppSelector } from "@/store/hooks";
import { selectPipelines } from "@/store/reducers/pipelines";
import { selectModels } from "@/store/reducers/models";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Home, ChevronDown, ChevronRight } from "lucide-react";
import { gvaMetaConvertConfig } from "@/features/pipeline-editor/nodes/GVAMetaConvertNode.config.ts";
import { gvaTrackConfig } from "@/features/pipeline-editor/nodes/GVATrackNode.config.ts";
import { gvaClassifyConfig } from "@/features/pipeline-editor/nodes/GVAClassifyNode.config.ts";
import { gvaDetectConfig } from "@/features/pipeline-editor/nodes/GVADetectNode.config.ts";
import pipeline0 from "@/assets/pipeline_0.png";
import pipeline1 from "@/assets/pipeline_1.png";
import pipeline2 from "@/assets/pipeline_2.png";
import pipeline3 from "@/assets/pipeline_3.png";
import pipeline4 from "@/assets/pipeline_4.png";
import pipeline5 from "@/assets/pipeline_5.png";
import type { Pipeline } from "@/api/api.generated";
import { ParticipationSlider } from "@/features/pipeline-tests/ParticipationSlider.tsx";
import { StreamsSlider } from "@/features/pipeline-tests/StreamsSlider.tsx";
import SaveOutputWarning from "@/features/pipeline-tests/SaveOutputWarning.tsx";
import { TestProgressIndicator } from "@/features/pipeline-tests/TestProgressIndicator.tsx";
import { PipelineStreamsSummary } from "@/features/pipeline-tests/PipelineStreamsSummary.tsx";
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

// Mapowanie typów węzłów na ich kategorie/tagi (z rzeczywistych definicji węzłów)
const nodeTypeToTag: Record<string, string> = {
  // Sources
  filesrc: "Source",
  v4l2src: "Source",
  videotestsrc: "Source",
  audiotestsrc: "Source",
  uridecodebin: "Source",

  // Decoders
  avdec_h264: "Decoder",
  avdec_h265: "Decoder",
  vah264dec: "Decoder",
  vah265dec: "Decoder",
  decodebin3: "Decoder",
  decodebin: "Decoder",
  vaapidecodebin: "Decoder",

  // Encoders
  vah264enc: "Encoder",

  // Demuxers/Muxers/Parsers
  qtdemux: "Demuxer",
  h264parse: "Parser",
  h265parse: "Parser",
  videoparse: "Parser",
  mp4mux: "Muxer",
  splitmuxsink: "Muxer",

  // GVA - Inference/Processing
  gvadetect: "Detection",
  gvaclassify: "Classification",
  gvainference: "Inference",
  gvatrack: "Tracking",
  gvawatermark: "Overlay",
  gvametaconvert: "Converter",
  gvametapublish: "Publisher",
  gvafpscounter: "Counter",

  // Video Processing
  videoconvert: "Converter",
  videoscale: "PostProc",
  vapostproc: "Transform",
  capsfilter: "Filter",

  // Sinks
  fakesink: "Sink",
  filesink: "Sink",
  autovideosink: "Sink",
  v4l2sink: "Sink",
  ximagesink: "Sink",
  xvimagesink: "Sink",

  // Other
  queue: "Buffer",
  queue2: "Buffer",
  tee: "Splitter",
  identity: "Identity",
  valve: "Valve",

  // Caps
  "video/x-raw": "Caps",
  "video/x-raw(memory:VAMemory)": "Caps",
};

interface PipelineSelection {
  pipelineId: string;
  stream_rate: number;
}

type NodePropertyConfig = {
  key: string;
  label: string;
  type: "text" | "number" | "boolean" | "select" | "textarea";
  defaultValue?: unknown;
  options?: string[] | readonly string[];
  description?: string;
  required?: boolean;
  params?: { [key: string]: string };
};

type NodeConfig = {
  editableProperties: NodePropertyConfig[];
};

const getNodeConfig = (nodeType: string): NodeConfig | null => {
  switch (nodeType) {
    case "gvametaconvert":
      return gvaMetaConvertConfig;
    case "gvatrack":
      return gvaTrackConfig;
    case "gvaclassify":
      return gvaClassifyConfig;
    case "gvadetect":
      return gvaDetectConfig;
    default:
      return null;
  }
};

const DemoMode = () => {
  const navigate = useNavigate();
  usePipelinesLoader();
  useModelsLoader();
  useDevicesLoader();
  const pipelines = useAppSelector(selectPipelines);
  const models = useAppSelector(selectModels);
  const history = useMetricHistory();
  const [runDensityTest, { isLoading: isRunning }] =
    useRunDensityTestMutation();
  const [runPerformanceTest, { isLoading: isPerformanceRunning }] =
    useRunPerformanceTestMutation();
  const [updatePipeline] = useUpdatePipelineMutation();
  const [pipelineSelections, setPipelineSelections] = useState<
    PipelineSelection[]
  >([]);
  const [fpsFloor, setFpsFloor] = useState<number>(30);
  const [densityJobId, setDensityJobId] = useState<string | null>(null);
  const [performanceJobId, setPerformanceJobId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{
    per_stream_fps: number | null;
    total_streams: number | null;
    streams_per_pipeline: PipelinePerformanceSpec[] | null;
    video_output_paths: { [key: string]: string[] } | null;
  } | null>(null);
  const [performanceResult, setPerformanceResult] = useState<{
    total_fps: number | null;
    per_stream_fps: number | null;
    video_output_paths: { [key: string]: string[] } | null;
    live_stream_urls: { [key: string]: string } | null;
  } | null>(null);
  const [videoOutputEnabled, setVideoOutputEnabled] = useState(false);
  const [performanceVideoOutputEnabled, setPerformanceVideoOutputEnabled] =
    useState(false);
  const [performanceLivePreviewEnabled, setPerformanceLivePreviewEnabled] =
    useState(false);
  const [performanceStreams, setPerformanceStreams] = useState<
    Record<string, number>
  >({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [performanceErrorMessage, setPerformanceErrorMessage] = useState<
    string | null
  >(null);
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
  const [activeTest, setActiveTest] = useState<
    "performance-test" | "density-test"
  >("density-test");
  const [lastRunTest, setLastRunTest] = useState<
    "performance-test" | "density-test"
  >("density-test");
  const isDensityRunning = isRunning;
  const isRunDisabled =
    activeTest === "performance-test"
      ? isPerformanceRunning || !!performanceJobId
      : isDensityRunning || !!densityJobId;
  const [selectedConfigPipelineId, setSelectedConfigPipelineId] = useState<
    string | null
  >(null);
  const [openNodeId, setOpenNodeId] = useState<string | null>(null);
  const [nodeDataEdits, setNodeDataEdits] = useState<
    Record<string, Record<string, unknown>>
  >({});

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
    { jobId: densityJobId! },
    {
      skip: !densityJobId,
      pollingInterval: 1000,
    },
  );

  const { data: performanceJobStatus } = useGetPerformanceJobStatusQuery(
    { jobId: performanceJobId! },
    {
      skip: !performanceJobId,
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
      setDensityJobId(null);
    } else if (jobStatus?.state === "ERROR" || jobStatus?.state === "ABORTED") {
      console.error("Test failed:", jobStatus.error_message);
      setErrorMessage(jobStatus.error_message || "Test failed");
      setTestResult(null);
      setDensityJobId(null);
    }
  }, [jobStatus, history]);

  useEffect(() => {
    if (performanceJobStatus?.state === "COMPLETED") {
      setPerformanceResult({
        total_fps: performanceJobStatus.total_fps,
        per_stream_fps: performanceJobStatus.per_stream_fps,
        video_output_paths: performanceJobStatus.video_output_paths,
        live_stream_urls: performanceJobStatus.live_stream_urls,
      });
      setPerformanceErrorMessage(null);
      setPerformanceJobId(null);
    } else if (
      performanceJobStatus?.state === "ERROR" ||
      performanceJobStatus?.state === "ABORTED"
    ) {
      console.error(
        "Performance test failed:",
        performanceJobStatus.error_message,
      );
      setPerformanceErrorMessage(
        performanceJobStatus.error_message || "Test failed",
      );
      setPerformanceResult(null);
      setPerformanceJobId(null);
    }
  }, [performanceJobStatus]);

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

  useEffect(() => {
    if (pipelineSelections.length === 0) return;

    setPerformanceStreams((prev) => {
      const next = { ...prev };
      let changed = false;
      const validIds = new Set(
        pipelineSelections.map((selection) => selection.pipelineId),
      );

      pipelineSelections.forEach((selection) => {
        if (next[selection.pipelineId] == null) {
          next[selection.pipelineId] = 8;
          changed = true;
        }
      });

      Object.keys(next).forEach((pipelineId) => {
        if (!validIds.has(pipelineId)) {
          delete next[pipelineId];
          changed = true;
        }
      });

      return changed ? next : prev;
    });
  }, [pipelineSelections]);

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

  const handlePerformanceStreamsChange = (
    pipelineId: string,
    streams: number,
  ) => {
    setPerformanceStreams((prev) => ({
      ...prev,
      [pipelineId]: streams,
    }));
  };

  const handleRunTest = async () => {
    if (pipelineSelections.length === 0) return;

    setTestStarted(true);
    setLastRunTest(activeTest);

    try {
      for (const selection of pipelineSelections) {
        const pipeline = pipelines.find((p) => p.id === selection.pipelineId);
        if (!pipeline?.pipeline_graph) continue;

        let hasChanges = false;
        const getDefaultModelForNode = (nodeType: string) => {
          const category =
            nodeType === "gvadetect"
              ? "detection"
              : nodeType === "gvaclassify"
                ? "classification"
                : null;

          if (!category) return null;
          const match = models.find((model) => model.category === category);
          return match ? (match.display_name ?? match.name) : null;
        };
        const updatedNodes = pipeline.pipeline_graph.nodes.map((node) => {
          const edits = nodeDataEdits[node.id];
          const mergedData = {
            ...node.data,
            ...(edits ?? {}),
          } as Record<string, unknown>;

          const currentModel =
            mergedData.model === null || mergedData.model === undefined
              ? ""
              : String(mergedData.model);
          if (
            (node.type === "gvadetect" || node.type === "gvaclassify") &&
            currentModel.trim() === ""
          ) {
            const defaultModel = getDefaultModelForNode(node.type);
            if (defaultModel) {
              mergedData.model = defaultModel;
            }
          }

          const shouldUpdate =
            !!edits ||
            (mergedData.model !== node.data?.model &&
              (node.type === "gvadetect" || node.type === "gvaclassify"));

          if (!shouldUpdate) return node;
          hasChanges = true;

          const normalizedData = Object.fromEntries(
            Object.entries(mergedData).map(([key, value]) => [
              key,
              value === null || value === undefined ? "" : String(value),
            ]),
          ) as { [key: string]: string };

          return {
            ...node,
            data: normalizedData,
          };
        });

        if (hasChanges) {
          await updatePipeline({
            pipelineId: pipeline.id,
            pipelineUpdate: {
              pipeline_graph: {
                nodes: updatedNodes,
                edges: pipeline.pipeline_graph.edges ?? [],
              },
            },
          }).unwrap();
        }
      }
    } catch (err) {
      console.error("Failed to update pipeline before test:", err);
      if (activeTest === "performance-test") {
        setPerformanceErrorMessage("Failed to update pipeline configuration");
      } else {
        setErrorMessage("Failed to update pipeline configuration");
      }
      return;
    }

    if (activeTest === "performance-test") {
      setPerformanceResult(null);
      setPerformanceErrorMessage(null);
      try {
        const outputMode = performanceLivePreviewEnabled
          ? "live_stream"
          : performanceVideoOutputEnabled
            ? "file"
            : "disabled";

        const result = await runPerformanceTest({
          performanceTestSpecInput: {
            execution_config: {
              output_mode: outputMode,
              max_runtime: 0,
            },
            pipeline_performance_specs: pipelineSelections.map((selection) => ({
              id: selection.pipelineId,
              streams: performanceStreams[selection.pipelineId] ?? 8,
            })),
          },
        }).unwrap();
        setPerformanceJobId(result.job_id);
      } catch (err) {
        console.error("Failed to run performance test:", err);
      }
      return;
    }

    setTestResult(null);
    setErrorMessage(null);
    try {
      const result = await runDensityTest({
        densityTestSpec: {
          execution_config: {
            output_mode: videoOutputEnabled ? "file" : "disabled",
            max_runtime: 0,
          },
          fps_floor: fpsFloor,
          pipeline_density_specs: pipelineSelections.map((selection) => ({
            id: selection.pipelineId,
            stream_rate: selection.stream_rate,
          })),
        },
      }).unwrap();
      setDensityJobId(result.job_id);
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
                      const selections = Array.from(
                        selectedModels.values(),
                      ).map((id) => ({
                        pipelineId: id,
                        stream_rate: 50,
                      }));
                      setPipelineSelections(selections);
                      // Set first pipeline as selected for configuration
                      setSelectedConfigPipelineId(selections[0].pipelineId);
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
            <div className="grid grid-cols-2 grid-rows-[0.6fr_1.4fr] gap-4 h-full p-4 animate-[fadeIn_0.6s_ease-out]">
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
                    const isSelected =
                      selectedConfigPipelineId === selection.pipelineId;

                    return (
                      <Card
                        key={selection.pipelineId}
                        onClick={() =>
                          setSelectedConfigPipelineId(selection.pipelineId)
                        }
                        className={`flex flex-col border bg-gradient-to-br from-slate-800/90 via-slate-750/80 to-slate-800/90 backdrop-blur-md overflow-hidden w-44 shadow-lg hover:shadow-xl transition-all cursor-pointer ${
                          isSelected
                            ? "border-blue-500 ring-2 ring-blue-500/50"
                            : "border-slate-400/40 hover:border-blue-500/60 opacity-50 grayscale"
                        }`}
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
                className={`rounded-xl bg-gradient-to-br from-slate-900/90 via-slate-800/70 to-slate-900/90 border p-4 backdrop-blur-md flex flex-col min-h-0 ${colors.testBorder}`}
              >
                <p
                  className={`text-sm uppercase font-bold tracking-wider mb-3 ${colors.testTitle}`}
                >
                  Pipeline Configuration
                </p>
                <div className="flex-1 min-h-0 overflow-y-auto pr-1">
                  {selectedConfigPipelineId ? (
                    (() => {
                      const pipeline = pipelines.find(
                        (p) => p.id === selectedConfigPipelineId,
                      );
                      if (!pipeline) return null;

                      return (
                        <>
                          <Accordion
                            type="single"
                            collapsible
                            className="w-full space-y-2"
                          >
                            {pipeline.pipeline_graph?.nodes?.map((node) => {
                              const nodeTag = nodeTypeToTag[node.type] || null;
                              const nodeConfig = getNodeConfig(node.type);
                              const editableProperties =
                                nodeConfig?.editableProperties ?? [];

                              const dataEntries = nodeConfig
                                ? editableProperties.map((prop) => [
                                    prop.key,
                                    node.data[prop.key] ?? prop.defaultValue,
                                    prop,
                                  ])
                                : Object.entries(node.data ?? {})
                                    .filter(
                                      ([key]) =>
                                        !["label"].includes(key) &&
                                        !key.startsWith("__"),
                                    )
                                    .map(([key, value]) => [key, value, null]);

                              const getEditedValue = (
                                nodeId: string,
                                key: string,
                                originalValue: unknown,
                              ) => {
                                return (
                                  nodeDataEdits[nodeId]?.[key] ?? originalValue
                                );
                              };

                              const handleValueChange = (
                                nodeId: string,
                                key: string,
                                value: unknown,
                              ) => {
                                setNodeDataEdits((prev) => ({
                                  ...prev,
                                  [nodeId]: {
                                    ...prev[nodeId],
                                    [key]: value,
                                  },
                                }));
                              };

                              if (dataEntries.length === 0) {
                                return null;
                              }

                              return (
                                <AccordionItem
                                  key={node.id}
                                  value={node.id}
                                  className="bg-slate-950/90 border border-slate-400/40 rounded-lg px-3 overflow-hidden"
                                >
                                  <AccordionTrigger className="hover:no-underline py-2">
                                    <div className="flex flex-col items-start">
                                      {nodeTag ? (
                                        <>
                                          <span className="font-medium text-white">
                                            {nodeTag}
                                          </span>
                                          <span className="text-xs text-slate-400 font-light">
                                            {node.type}
                                          </span>
                                        </>
                                      ) : (
                                        <span className="font-medium text-white">
                                          {node.type}
                                        </span>
                                      )}
                                    </div>
                                  </AccordionTrigger>
                                  <AccordionContent>
                                    <div className="space-y-3 pb-2">
                                      {dataEntries.map(
                                        ([key, value, propConfig]) => {
                                          const currentValue = getEditedValue(
                                            node.id,
                                            String(key),
                                            value,
                                          );
                                          const config =
                                            propConfig as NodePropertyConfig | null;

                                          return (
                                            <div
                                              key={String(key)}
                                              className="space-y-1"
                                            >
                                              <label className="text-xs font-medium text-slate-300 block">
                                                {config?.label ?? String(key)}
                                              </label>
                                              {String(key) === "model" ? (
                                                <select
                                                  value={String(
                                                    currentValue ?? "",
                                                  )}
                                                  onChange={(e) =>
                                                    handleValueChange(
                                                      node.id,
                                                      String(key),
                                                      e.target.value,
                                                    )
                                                  }
                                                  className="w-full px-2 py-1.5 bg-slate-900/90 border border-slate-400/40 rounded text-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
                                                >
                                                  <option value="">
                                                    Select {config?.label}
                                                  </option>
                                                  {models
                                                    .filter(
                                                      (model) =>
                                                        model.category ===
                                                        config?.params?.filter,
                                                    )
                                                    .map((model) => (
                                                      <option
                                                        key={model.name}
                                                        value={
                                                          model.display_name ??
                                                          model.name
                                                        }
                                                      >
                                                        {model.display_name ??
                                                          model.name}
                                                      </option>
                                                    ))}
                                                </select>
                                              ) : config?.type === "select" ? (
                                                <select
                                                  value={String(
                                                    currentValue ?? "",
                                                  )}
                                                  onChange={(e) =>
                                                    handleValueChange(
                                                      node.id,
                                                      String(key),
                                                      e.target.value,
                                                    )
                                                  }
                                                  className="w-full px-2 py-1.5 bg-slate-900/90 border border-slate-400/40 rounded text-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
                                                >
                                                  {config.options?.map(
                                                    (option) => (
                                                      <option
                                                        key={option}
                                                        value={option}
                                                      >
                                                        {option}
                                                      </option>
                                                    ),
                                                  )}
                                                </select>
                                              ) : config?.type === "boolean" ? (
                                                <div className="flex items-center gap-2">
                                                  <Checkbox
                                                    checked={
                                                      currentValue === true ||
                                                      currentValue === "true"
                                                    }
                                                    onCheckedChange={(
                                                      checked,
                                                    ) =>
                                                      handleValueChange(
                                                        node.id,
                                                        String(key),
                                                        checked,
                                                      )
                                                    }
                                                    className={colors.checkbox}
                                                  />
                                                  <span className="text-xs text-slate-400">
                                                    {config.description}
                                                  </span>
                                                </div>
                                              ) : config?.type ===
                                                "textarea" ? (
                                                <textarea
                                                  value={String(
                                                    currentValue ?? "",
                                                  )}
                                                  onChange={(e) =>
                                                    handleValueChange(
                                                      node.id,
                                                      String(key),
                                                      e.target.value,
                                                    )
                                                  }
                                                  className="w-full px-2 py-1.5 bg-slate-900/90 border border-slate-400/40 rounded text-slate-200 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 resize-y min-h-[60px]"
                                                  placeholder={
                                                    config.description
                                                  }
                                                />
                                              ) : config?.type === "number" ? (
                                                <input
                                                  type="number"
                                                  value={String(
                                                    currentValue ?? "",
                                                  )}
                                                  onChange={(e) =>
                                                    handleValueChange(
                                                      node.id,
                                                      String(key),
                                                      parseFloat(
                                                        e.target.value,
                                                      ),
                                                    )
                                                  }
                                                  className="w-full px-2 py-1.5 bg-slate-900/90 border border-slate-400/40 rounded text-slate-200 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
                                                  placeholder={
                                                    config.description
                                                  }
                                                />
                                              ) : (
                                                <input
                                                  type="text"
                                                  value={String(
                                                    currentValue ?? "",
                                                  )}
                                                  onChange={(e) =>
                                                    handleValueChange(
                                                      node.id,
                                                      String(key),
                                                      e.target.value,
                                                    )
                                                  }
                                                  className="w-full px-2 py-1.5 bg-slate-900/90 border border-slate-400/40 rounded text-slate-200 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
                                                  placeholder={
                                                    config?.description ??
                                                    "Enter value"
                                                  }
                                                />
                                              )}
                                            </div>
                                          );
                                        },
                                      )}
                                    </div>
                                  </AccordionContent>
                                </AccordionItem>
                              );
                            })}
                          </Accordion>

                          {/* Run Configuration Section */}
                          <div className="mt-4 border-t border-slate-400/30 pt-4">
                            <p
                              className={`text-sm uppercase font-bold tracking-wider mb-3 ${colors.testTitle}`}
                            >
                              Run Configuration
                            </p>
                            <div className="w-full">
                              <div className="inline-flex rounded-lg border border-slate-400/40 bg-slate-950/70 p-1 mb-3">
                                <button
                                  type="button"
                                  onClick={() =>
                                    setActiveTest("performance-test")
                                  }
                                  className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${
                                    activeTest === "performance-test"
                                      ? "bg-blue-600 text-white"
                                      : "text-slate-300 hover:text-white"
                                  }`}
                                >
                                  Performance Test
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setActiveTest("density-test")}
                                  className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${
                                    activeTest === "density-test"
                                      ? "bg-blue-600 text-white"
                                      : "text-slate-300 hover:text-white"
                                  }`}
                                >
                                  Density Test
                                </button>
                              </div>

                              {activeTest === "performance-test" ? (
                                <div className="bg-slate-950/90 border border-slate-400/40 rounded-lg px-3 py-3">
                                  <div className="space-y-3">
                                    {/* Streams per pipeline */}
                                    <div className="space-y-2">
                                      {pipelineSelections.map((selection) => {
                                        const pipeline = pipelines.find(
                                          (p) => p.id === selection.pipelineId,
                                        );

                                        return (
                                          <div
                                            key={selection.pipelineId}
                                            className="rounded-md border border-slate-400/30 bg-slate-900/60 px-3 py-2"
                                          >
                                            <div className="flex items-center justify-between gap-2 mb-2">
                                              <span className="text-xs text-slate-300 font-semibold">
                                                {pipeline?.name ?? "Pipeline"}
                                              </span>
                                              <span className="text-[10px] text-slate-500">
                                                Streams
                                              </span>
                                            </div>
                                            <StreamsSlider
                                              value={
                                                performanceStreams[
                                                  selection.pipelineId
                                                ] ?? 8
                                              }
                                              onChange={(val) =>
                                                handlePerformanceStreamsChange(
                                                  selection.pipelineId,
                                                  val,
                                                )
                                              }
                                              min={1}
                                              max={64}
                                            />
                                          </div>
                                        );
                                      })}
                                    </div>

                                    {/* Live Preview + Save Output */}
                                    <div className="flex flex-wrap items-start gap-3">
                                      <div className="space-y-1 min-h-[72px]">
                                        <div className="flex items-center gap-2">
                                          <Checkbox
                                            checked={
                                              performanceLivePreviewEnabled
                                            }
                                            onCheckedChange={(checked) =>
                                              setPerformanceLivePreviewEnabled(
                                                checked === true,
                                              )
                                            }
                                            className={colors.checkbox}
                                          />
                                          <label className="text-xs text-slate-300">
                                            Enable live preview
                                          </label>
                                        </div>
                                      </div>

                                      <div className="space-y-1">
                                        <div className="flex items-center gap-2">
                                          <Checkbox
                                            checked={
                                              performanceVideoOutputEnabled
                                            }
                                            onCheckedChange={(checked) =>
                                              setPerformanceVideoOutputEnabled(
                                                checked === true,
                                              )
                                            }
                                            className={colors.checkbox}
                                          />
                                          <label className="text-xs text-slate-300">
                                            Save output
                                          </label>
                                        </div>
                                        {performanceVideoOutputEnabled && (
                                          <div className="mt-2">
                                            <SaveOutputWarning />
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              ) : (
                                <div className="bg-slate-950/90 border border-slate-400/40 rounded-lg px-3 py-3">
                                  <div className="space-y-3">
                                    {/* Participation rate per pipeline */}
                                    <div className="space-y-2">
                                      {pipelineSelections.map((selection) => {
                                        const pipeline = pipelines.find(
                                          (p) => p.id === selection.pipelineId,
                                        );

                                        return (
                                          <div
                                            key={selection.pipelineId}
                                            className="rounded-md border border-slate-400/30 bg-slate-900/60 px-3 py-2"
                                          >
                                            <div className="flex items-center justify-between gap-2 mb-2">
                                              <span className="text-xs text-slate-300 font-semibold">
                                                {pipeline?.name ?? "Pipeline"}
                                              </span>
                                              <span className="text-[10px] text-slate-500">
                                                Participation rate
                                              </span>
                                            </div>
                                            <ParticipationSlider
                                              value={selection.stream_rate}
                                              onChange={(val) =>
                                                handleStreamRateChange(
                                                  selection.pipelineId,
                                                  val,
                                                )
                                              }
                                              min={0}
                                              max={100}
                                            />
                                          </div>
                                        );
                                      })}
                                    </div>

                                    {/* FPS Floor + Video Output */}
                                    <div className="flex flex-wrap items-start gap-3">
                                      <div className="space-y-1 min-h-[72px]">
                                        <label className="text-xs font-medium text-slate-300 block">
                                          Target FPS
                                        </label>
                                        <input
                                          type="number"
                                          value={fpsFloor}
                                          onChange={(e) =>
                                            setFpsFloor(
                                              parseFloat(e.target.value) || 0,
                                            )
                                          }
                                          className="w-28 px-2 py-1.5 bg-slate-900/90 border border-slate-400/40 rounded text-slate-200 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
                                          placeholder="Minimum FPS threshold"
                                          min={0}
                                        />
                                      </div>

                                      <div className="space-y-1">
                                        <div className="flex items-center gap-2">
                                          <Checkbox
                                            checked={videoOutputEnabled}
                                            onCheckedChange={(checked) =>
                                              setVideoOutputEnabled(!!checked)
                                            }
                                            className={colors.checkbox}
                                          />
                                          <label className="text-xs text-slate-300">
                                            Save output
                                          </label>
                                        </div>
                                        {videoOutputEnabled && (
                                          <div className="mt-2">
                                            <SaveOutputWarning />
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              )}

                              {/* Run Button */}
                              <button
                                onClick={handleRunTest}
                                disabled={isRunDisabled}
                                className={`w-full relative px-4 py-2.5 text-white rounded-lg font-bold tracking-wider text-sm shadow-lg transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed mt-3 ${colors.runButton}`}
                              >
                                <div
                                  className={`absolute inset-0 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-300 ${colors.runButtonOverlay}`}
                                ></div>
                                <span className="relative">
                                  {isRunDisabled ? "Running..." : "Run Test"}
                                </span>
                              </button>
                            </div>
                          </div>
                        </>
                      );
                    })()
                  ) : (
                    <div className="flex-1 flex items-center justify-center text-slate-400">
                      <p className="text-sm">Select a pipeline to configure</p>
                    </div>
                  )}
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
                  {lastRunTest === "performance-test" ? (
                    <div className="space-y-3">
                      {performanceJobId && performanceJobStatus && (
                        <div className="rounded-lg border border-neutral-800 bg-neutral-950/60 p-3">
                          <p className="text-sm font-bold text-white mb-1">
                            Test Status: {performanceJobStatus.state}
                          </p>
                          {performanceJobStatus.state === "RUNNING" && (
                            <div className="mt-2">
                              <div className="mb-2 flex items-center gap-2">
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
                                  Running performance test...
                                </span>
                              </div>
                              <TestProgressIndicator />
                            </div>
                          )}
                        </div>
                      )}

                      {performanceErrorMessage && (
                        <div className="rounded-lg border border-neutral-800 bg-neutral-950/60 p-3">
                          <p className="text-sm font-bold text-white mb-1">
                            Test Failed
                          </p>
                          <p className="text-xs text-neutral-300">
                            {performanceErrorMessage}
                          </p>
                        </div>
                      )}

                      {!performanceResult &&
                        !performanceJobId &&
                        !performanceErrorMessage && (
                          <div className="flex items-center justify-center h-full text-slate-400">
                            <p className="text-sm">
                              Results will appear here after running the test
                            </p>
                          </div>
                        )}

                      {performanceResult && (
                        <div className="space-y-3">
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
                                  Total FPS
                                </p>
                                <p
                                  className={`text-xl font-bold ${colors.summaryFpsText}`}
                                >
                                  {performanceResult.total_fps?.toFixed(2) ??
                                    "N/A"}
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
                                  Per Stream FPS
                                </p>
                                <p
                                  className={`text-2xl font-bold ${colors.summaryStreamsValueText}`}
                                >
                                  {performanceResult.per_stream_fps?.toFixed(
                                    2,
                                  ) ?? "N/A"}
                                </p>
                              </div>
                            </div>
                          </div>

                          {performanceLivePreviewEnabled &&
                            performanceResult.live_stream_urls &&
                            Object.keys(performanceResult.live_stream_urls)
                              .length > 0 && (
                              <div className="space-y-2">
                                <p className="text-xs font-semibold text-slate-300">
                                  Live previews
                                </p>
                                <div className="grid grid-cols-1 gap-2">
                                  {Object.entries(
                                    performanceResult.live_stream_urls,
                                  ).map(([pipelineId, url]) => (
                                    <div
                                      key={pipelineId}
                                      className="rounded-md border border-slate-400/30 bg-slate-900/60 p-2"
                                    >
                                      <p className="text-[10px] text-slate-400 mb-2">
                                        <PipelineName pipelineId={pipelineId} />
                                      </p>
                                      <video
                                        controls
                                        className="w-full"
                                        src={url}
                                      />
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                          {performanceVideoOutputEnabled &&
                            performanceResult.video_output_paths &&
                            Object.keys(performanceResult.video_output_paths)
                              .length > 0 && (
                              <div className="space-y-2">
                                <p className="text-xs font-semibold text-slate-300">
                                  Output Videos
                                </p>
                                <div className="grid grid-cols-1 gap-2">
                                  {Object.entries(
                                    performanceResult.video_output_paths,
                                  ).map(([pipelineId, paths]) => {
                                    const videoPath =
                                      paths && paths.length > 0
                                        ? [...paths].pop()
                                        : null;

                                    return (
                                      <div
                                        key={pipelineId}
                                        className="rounded-md border border-slate-400/30 bg-slate-900/60 overflow-hidden"
                                      >
                                        <div className="px-3 py-2 border-b border-slate-400/20">
                                          <p className="text-[10px] text-slate-400">
                                            <PipelineName
                                              pipelineId={pipelineId}
                                            />
                                          </p>
                                        </div>
                                        {videoPath ? (
                                          <video
                                            controls
                                            className="w-full"
                                            src={`/assets${videoPath}`}
                                          >
                                            Your browser does not support the
                                            video tag.
                                          </video>
                                        ) : (
                                          <div className="p-3 text-center text-xs text-slate-400">
                                            no streams
                                          </div>
                                        )}
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            )}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {densityJobId && jobStatus && (
                        <div className="rounded-lg border border-neutral-800 bg-neutral-950/60 p-3">
                          <p className="text-sm font-bold text-white mb-1">
                            Test Status: {jobStatus.state}
                          </p>
                          {jobStatus.state === "RUNNING" && (
                            <div className="mt-2">
                              <div className="mb-2 flex items-center gap-2">
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
                                  Running density test...
                                </span>
                              </div>
                              <TestProgressIndicator />
                            </div>
                          )}
                        </div>
                      )}

                      {errorMessage && (
                        <div className="rounded-lg border border-neutral-800 bg-neutral-950/60 p-3">
                          <p className="text-sm font-bold text-white mb-1">
                            Test Failed
                          </p>
                          <p className="text-xs text-neutral-300">
                            {errorMessage}
                          </p>
                        </div>
                      )}

                      {!testResult && !densityJobId && !errorMessage && (
                        <div className="flex items-center justify-center h-full text-slate-400">
                          <p className="text-sm">
                            Results will appear here after running the test
                          </p>
                        </div>
                      )}

                      {testResult && (
                        <div className="space-y-3">
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
                                  {testResult.per_stream_fps?.toFixed(2) ??
                                    "N/A"}
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

                          {testResult.streams_per_pipeline && (
                            <div className="rounded-lg border border-slate-400/30 bg-slate-900/60 p-2">
                              <p className="text-xs text-slate-300 font-semibold mb-2">
                                Streams per Pipeline
                              </p>
                              <PipelineStreamsSummary
                                streamsPerPipeline={
                                  testResult.streams_per_pipeline
                                }
                                pipelines={pipelines ?? []}
                              />
                            </div>
                          )}

                          {videoOutputEnabled &&
                            testResult.video_output_paths &&
                            Object.keys(testResult.video_output_paths).length >
                              0 && (
                              <div className="space-y-2">
                                <p className="text-xs font-semibold text-slate-300">
                                  Output Videos
                                </p>
                                <div className="grid grid-cols-1 gap-2">
                                  {Object.entries(
                                    testResult.video_output_paths,
                                  ).map(([pipelineId, paths]) => {
                                    const videoPath =
                                      paths && paths.length > 0
                                        ? [...paths].pop()
                                        : null;

                                    return (
                                      <div
                                        key={pipelineId}
                                        className="rounded-md border border-slate-400/30 bg-slate-900/60 overflow-hidden"
                                      >
                                        <div className="px-3 py-2 border-b border-slate-400/20">
                                          <p className="text-[10px] text-slate-400">
                                            <PipelineName
                                              pipelineId={pipelineId}
                                            />
                                          </p>
                                        </div>
                                        {videoPath ? (
                                          <video
                                            controls
                                            className="w-full"
                                            src={`/assets${videoPath}`}
                                          >
                                            Your browser does not support the
                                            video tag.
                                          </video>
                                        ) : (
                                          <div className="p-3 text-center text-xs text-slate-400">
                                            no streams
                                          </div>
                                        )}
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            )}
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
