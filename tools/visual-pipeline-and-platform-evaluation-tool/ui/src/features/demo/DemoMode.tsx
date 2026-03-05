import { type WheelEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  type PipelineStreamSpec,
  useGetVideosQuery,
  useGetDensityJobStatusQuery,
  useGetPerformanceJobStatusQuery,
  useRunDensityTestMutation,
  useRunPerformanceTestMutation,
  useStopDensityTestJobMutation,
  useStopPerformanceTestJobMutation,
} from "@/api/api.generated.ts";
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
import { Home, ChevronRight, ChevronLeft } from "lucide-react";
import { gvaMetaConvertConfig } from "@/features/pipeline-editor/nodes/GVAMetaConvertNode.config.ts";
import { gvaTrackConfig } from "@/features/pipeline-editor/nodes/GVATrackNode.config.ts";
import { gvaClassifyConfig } from "@/features/pipeline-editor/nodes/GVAClassifyNode.config.ts";
import { gvaDetectConfig } from "@/features/pipeline-editor/nodes/GVADetectNode.config.ts";
import thumbnailPlaceholder from "@/assets/thumbnail_placeholder.png";
import type { Pipeline } from "@/api/api.generated";
import { useMetricHistory } from "@/hooks/useMetricHistory.ts";
import { TestProgressIndicator } from "@/features/pipeline-tests/TestProgressIndicator.tsx";
import { ParticipationSlider } from "@/features/pipeline-tests/ParticipationSlider.tsx";
import { StreamsSlider } from "@/features/pipeline-tests/StreamsSlider.tsx";
import { PipelineStreamsSummary } from "@/features/pipeline-tests/PipelineStreamsSummary.tsx";
import { useNavigate } from "react-router";
import { usePipelinesLoader } from "@/hooks/usePipelines.ts";
import { useModelsLoader } from "@/hooks/useModels.ts";
import { useDevicesLoader } from "@/hooks/useDevices.ts";
import { useStreamRateChange } from "@/hooks/useStreamRateChange.ts";
import { Toaster } from "@/components/ui/sonner.tsx";
import { BubbleBackground } from "@/components/ui/shadcn-io/bubble-background";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import WebRTCVideoPlayer from "@/features/webrtc/WebRTCVideoPlayer.tsx";

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

const CheckboxInfoHint = ({
  description,
  muted = false,
}: {
  description: string;
  muted?: boolean;
}) => (
  <Tooltip>
    <TooltipTrigger asChild>
      <span
        className={`inline-flex h-4 w-4 shrink-0 cursor-help select-none items-center justify-center rounded-full border text-[10px] font-bold leading-none ${
          muted
            ? "border-slate-600 text-slate-500"
            : "border-slate-400/70 text-slate-300"
        }`}
      >
        i
      </span>
    </TooltipTrigger>
    <TooltipContent
      side="right"
      sideOffset={8}
      className="max-w-[260px] border border-slate-700 bg-slate-900 text-slate-100"
    >
      {description}
    </TooltipContent>
  </Tooltip>
);

const DemoMode = () => {
  const navigate = useNavigate();
  usePipelinesLoader();
  useModelsLoader();
  useDevicesLoader();
  const pipelines = useAppSelector(selectPipelines);
  const models = useAppSelector(selectModels);
  const { data: videos = [] } = useGetVideosQuery();
  const [runDensityTest, { isLoading: isRunning }] =
    useRunDensityTestMutation();
  const [runPerformanceTest, { isLoading: isPerformanceRunning }] =
    useRunPerformanceTestMutation();
  const [stopDensityTestJob] = useStopDensityTestJobMutation();
  const [stopPerformanceTestJob] = useStopPerformanceTestJobMutation();
  const [pipelineSelections, setPipelineSelections] = useState<
    PipelineSelection[]
  >([]);
  const [fpsFloor, setFpsFloor] = useState<number>(30);
  const [densityJobId, setDensityJobId] = useState<string | null>(null);
  const handleStreamRateChange = useStreamRateChange(setPipelineSelections);
  const [performanceJobId, setPerformanceJobId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{
    per_stream_fps: number | null;
    total_streams: number | null;
    streams_per_pipeline: PipelineStreamSpec[] | null;
    video_output_paths: { [key: string]: string[] } | null;
  } | null>(null);
  const [performanceResult, setPerformanceResult] = useState<{
    total_fps: number | null;
    per_stream_fps: number | null;
    video_output_paths: { [key: string]: string[] } | null;
    live_stream_urls: { [key: string]: string } | null;
  } | null>(null);
  const [performanceLivePreviewEnabled, setPerformanceLivePreviewEnabled] =
    useState(true);
  const [performanceStreams, setPerformanceStreams] = useState<
    Record<string, number>
  >({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [performanceErrorMessage, setPerformanceErrorMessage] = useState<
    string | null
  >(null);
  const [testStarted, setTestStarted] = useState(false);
  const [testStartTimestamp, setTestStartTimestamp] = useState<number | null>(
    null,
  );
  const history = useMetricHistory();
  const [metricHistorySnapshot, setMetricHistorySnapshot] = useState<
    typeof history
  >([]);
  const [metricsFrozenForJobId, setMetricsFrozenForJobId] = useState<
    string | null
  >(null);
  const [frozenPerStreamFps, setFrozenPerStreamFps] = useState<number | null>(
    null,
  );
  const [selectedModels, setSelectedModels] = useState<Map<string, string>>(
    new Map(),
  ); // Map<baseName, selectedPipelineId>
  const [demoStep, setDemoStep] = useState<"selection" | "configuration">(
    "selection",
  );
  const [openConfigSection, setOpenConfigSection] =
    useState<string>("pipeline-config");
  const [activeTest, setActiveTest] = useState<
    "performance-test" | "density-test"
  >("performance-test");
  const [lastRunTest, setLastRunTest] = useState<
    "performance-test" | "density-test"
  >("performance-test");
  const isDensityRunning = isRunning;
  const isRunDisabled =
    activeTest === "performance-test"
      ? isPerformanceRunning || !!performanceJobId
      : isDensityRunning || !!densityJobId;
  const isReadOnly = isRunDisabled;
  const [selectedConfigPipelineId, setSelectedConfigPipelineId] = useState<
    string | null
  >(null);
  const [carouselIndex, setCarouselIndex] = useState(0);
  const [previewCarouselIndex, setPreviewCarouselIndex] = useState(0);
  const [nodeDataEdits, setNodeDataEdits] = useState<
    Record<string, Record<string, unknown>>
  >({});
  const [selectedVariantByPipelineId, setSelectedVariantByPipelineId] =
    useState<Record<string, string>>({});
  const videoFilenames = useMemo(
    () => videos.map((video) => video.filename),
    [videos],
  );
  const getFilenameFromPath = (value: unknown): string => {
    const stringValue = String(value ?? "");
    if (!stringValue) return "";
    const normalized = stringValue.replace(/\\/g, "/");
    const segments = normalized.split("/");
    return segments.at(-1) ?? stringValue;
  };
  const getNodeEditKey = (
    pipelineId: string,
    variantId: string,
    nodeId: string,
  ) => `${pipelineId}::${variantId}::${nodeId}`;
  const getSelectedVariantForPipeline = (pipelineId: string) => {
    const pipeline = pipelines.find((p) => p.id === pipelineId);
    if (!pipeline || pipeline.variants.length === 0) return null;

    const selectedVariantId = selectedVariantByPipelineId[pipelineId];
    return (
      pipeline.variants.find((variant) => variant.id === selectedVariantId) ??
      pipeline.variants[0]
    );
  };
  const inferenceNodeTypes = new Set([
    "gvadetect",
    "gvaclassify",
    "gvainference",
  ]);
  const inferenceOnlyKeys = new Set([
    "model",
    "model-proc",
    "labels",
    "labels-file",
    "model-instance-id",
    "device",
    "pre-process-backend",
    "nireq",
    "ie-config",
    "batch-size",
    "inference-interval",
    "inference-region",
    "reclassify-interval",
    "threshold",
    "object-class",
  ]);
  const sanitizeNodeData = (
    nodeType: string,
    data: Record<string, unknown>,
  ) => {
    const sanitized = { ...data } as Record<string, unknown>;

    if (!inferenceNodeTypes.has(nodeType)) {
      inferenceOnlyKeys.forEach((key) => {
        if (Object.prototype.hasOwnProperty.call(sanitized, key)) {
          delete sanitized[key];
        }
      });
    } else if (
      Object.prototype.hasOwnProperty.call(sanitized, "inference-interval")
    ) {
      const intervalRaw = sanitized["inference-interval"];
      const intervalValue = Number(intervalRaw);
      if (!Number.isFinite(intervalValue) || intervalValue < 1) {
        sanitized["inference-interval"] = "1";
      }
    }

    if (inferenceNodeTypes.has(nodeType)) {
      const regionValue = sanitized["inference-region"];
      const normalizedRegion =
        regionValue === null || regionValue === undefined
          ? ""
          : String(regionValue);
      if (normalizedRegion !== "roi-list") {
        delete sanitized["object-class"];
      }
    }

    return sanitized;
  };
  const showResultsPanel = testStarted;
  const isTestFinished =
    lastRunTest === "performance-test"
      ? !performanceJobId && (!!performanceResult || !!performanceErrorMessage)
      : !densityJobId && (!!testResult || !!errorMessage);
  const isPipelineConfigOpen = openConfigSection === "pipeline-config";
  const pipelineConfigContainerMaxHeightClass = "max-h-[58vh]";
  const pipelineConfigMaxHeightClass = isPipelineConfigOpen
    ? "max-h-[32vh]"
    : "max-h-[44vh]";
  const runConfigMaxHeightClass = "max-h-[31vh]";

  // Show preview panel only when there's actual content to display
  const hasLiveStreamContent =
    testStarted &&
    lastRunTest === "performance-test" &&
    !!performanceJobId &&
    performanceLivePreviewEnabled &&
    performanceResult?.live_stream_urls &&
    Object.keys(performanceResult.live_stream_urls).length > 0;

  const showPreviewPanel = hasLiveStreamContent;

  const showPreRunLayout = !testStarted;
  const gridColumnsStyle = {
    gridTemplateColumns: showResultsPanel ? "0.7fr 1.3fr" : "1fr 1fr",
    transition: "grid-template-columns 600ms ease",
  } as const;
  const frozenMetrics = metricHistorySnapshot;
  const hasFrozenMetrics = frozenMetrics.length > 0;
  type FrozenGpuMetrics = {
    compute: number | undefined;
    render: number | undefined;
    copy: number | undefined;
    video: number | undefined;
    videoEnhance: number | undefined;
    frequency: number | undefined;
    gpuPower: number | undefined;
    pkgPower: number | undefined;
  };

  const frozenMetricsSummary = useMemo<{
    fps: number;
    cpu: number;
    memory: number;
    availableGpuIds: string[];
    gpuDetailedMetrics: Record<string, FrozenGpuMetrics>;
  } | null>(() => {
    if (!hasFrozenMetrics) return null;

    const avg = (values: number[]) =>
      values.length > 0
        ? values.reduce((sum, value) => sum + value, 0) / values.length
        : 0;

    const fpsSeries = frozenMetrics.map((point) => point.fps ?? 0);
    const firstPositiveFpsIndex = fpsSeries.findIndex((value) => value > 0);
    const fpsValuesForAverage =
      firstPositiveFpsIndex >= 0
        ? fpsSeries.slice(firstPositiveFpsIndex)
        : fpsSeries;
    const fpsAvg = avg(fpsValuesForAverage);
    const cpuAvg = avg(frozenMetrics.map((point) => point.cpu ?? 0));
    const memoryAvg = avg(frozenMetrics.map((point) => point.memory ?? 0));

    const gpuIds = Array.from(
      new Set(frozenMetrics.flatMap((point) => Object.keys(point.gpus ?? {}))),
    ).sort();

    const gpuDetailedMetrics = gpuIds.reduce<Record<string, FrozenGpuMetrics>>(
      (acc, gpuId) => {
        const metricsPerPoint = frozenMetrics.map((point) => point.gpus[gpuId]);
        const mapMetric = (key: keyof (typeof metricsPerPoint)[number]) =>
          avg(
            metricsPerPoint
              .map((metric) => metric?.[key])
              .filter((value): value is number => value !== undefined),
          );

        acc[gpuId] = {
          compute: mapMetric("compute"),
          render: mapMetric("render"),
          copy: mapMetric("copy"),
          video: mapMetric("video"),
          videoEnhance: mapMetric("videoEnhance"),
          frequency: mapMetric("frequency"),
          gpuPower: mapMetric("gpuPower"),
          pkgPower: mapMetric("pkgPower"),
        };
        return acc;
      },
      {},
    );

    return {
      fps: frozenPerStreamFps ?? fpsAvg,
      cpu: cpuAvg,
      memory: memoryAvg,
      availableGpuIds: gpuIds,
      gpuDetailedMetrics,
    };
  }, [frozenMetrics, hasFrozenMetrics, frozenPerStreamFps]);

  const smoothScrollRef = useRef<{
    rafId: number;
    targetScrollTop: number;
    currentScrollTop: number;
    target: HTMLDivElement | null;
  }>({ rafId: 0, targetScrollTop: 0, currentScrollTop: 0, target: null });

  const handleFastScroll = (event: WheelEvent<HTMLDivElement>) => {
    const target = event.currentTarget;
    if (target.scrollHeight <= target.clientHeight) return;

    event.preventDefault();

    if (!smoothScrollRef.current.rafId) {
      smoothScrollRef.current.currentScrollTop = target.scrollTop;
      smoothScrollRef.current.targetScrollTop = target.scrollTop;
    }

    smoothScrollRef.current.targetScrollTop += event.deltaY;
    smoothScrollRef.current.targetScrollTop = Math.max(
      0,
      Math.min(
        target.scrollHeight - target.clientHeight,
        smoothScrollRef.current.targetScrollTop,
      ),
    );
    smoothScrollRef.current.target = target;

    if (smoothScrollRef.current.rafId) return;

    const animate = () => {
      const {
        target: rafTarget,
        targetScrollTop,
        currentScrollTop,
      } = smoothScrollRef.current;
      if (!rafTarget) {
        smoothScrollRef.current.rafId = 0;
        return;
      }

      const diff = targetScrollTop - currentScrollTop;
      if (Math.abs(diff) < 0.5) {
        rafTarget.scrollTop = targetScrollTop;
        smoothScrollRef.current.currentScrollTop = targetScrollTop;
        smoothScrollRef.current.rafId = 0;
        return;
      }

      const ease = 0.15;
      smoothScrollRef.current.currentScrollTop += diff * ease;
      rafTarget.scrollTop = smoothScrollRef.current.currentScrollTop;

      smoothScrollRef.current.rafId = requestAnimationFrame(animate);
    };

    smoothScrollRef.current.rafId = requestAnimationFrame(animate);
  };

  const performanceSummary = useMemo(() => {
    if (!performanceResult) return null;
    let total = performanceResult.total_fps;
    let perStream = performanceResult.per_stream_fps;
    if (total != null && perStream != null && total < perStream) {
      const tmp = total;
      total = perStream;
      perStream = tmp;
    }
    return { total, perStream };
  }, [performanceResult]);

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
    summaryFpsBorder:
      "border-energy-blue/60 shadow-lg shadow-energy-blue/20 ring-2 ring-energy-blue/30",
    summaryFpsGradient:
      "bg-gradient-to-r from-energy-blue/15 via-energy-blue-tint-1/15 to-energy-blue/15",
    summaryFpsText: "text-energy-blue-tint-1",
    summaryStreamsBorder:
      "border-energy-blue/60 shadow-lg shadow-energy-blue/20 ring-2 ring-energy-blue/30",
    summaryStreamsGradient:
      "bg-gradient-to-r from-energy-blue/15 via-energy-blue-tint-1/15 to-energy-blue/15",
    summaryStreamsText: "text-energy-blue-tint-1",
    summaryStreamsValueText: "text-white",
  };

  const getBasePipelineName = (name: string) => {
    const match = name.match(/^(.+?)\s*(\[.+?\])?$/);
    return match ? match[1].trim() : name;
  };

  const formatVariantDisplayName = (
    variantName: string | undefined,
    variantId: string,
  ) => {
    const rawName = (variantName ?? "").trim();
    const source = rawName || variantId;
    const normalized = source.toUpperCase();

    if (normalized === "CPU") return "CPU only";
    if (normalized === "GPU") return "GPU only";
    if (normalized === "NPU") return "NPU only";

    const deviceParts = normalized.split("_");
    const allowedParts = new Set(["CPU", "GPU", "NPU"]);
    if (
      deviceParts.length > 1 &&
      deviceParts.every((part) => allowedParts.has(part))
    ) {
      return `${deviceParts.join(" / ")} split`;
    }

    return source;
  };

  // Group pipelines by base name
  const groupedPipelines = pipelines.reduce(
    (acc, pipeline) => {
      const match = pipeline.name.match(/^(.+?)\s*(\[.+?\])?$/);
      const baseName = match ? match[1].trim() : pipeline.name;
      const tag = match && match[2] ? match[2].replace(/[[\]]/g, "") : null;

      const existing = acc.find((group) => group.baseName === baseName);
      if (existing) {
        if (tag) {
          existing.pipelines[tag] = pipeline;
        } else {
          // If no tag, add as "default" variant
          existing.pipelines["default"] = pipeline;
        }
      } else {
        acc.push({
          baseName,
          pipelines: tag ? { [tag]: pipeline } : { default: pipeline },
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
    if (!jobStatus || jobStatus.id !== densityJobId) {
      return;
    }

    if (jobStatus?.state === "COMPLETED") {
      setTestResult({
        per_stream_fps: jobStatus.per_stream_fps,
        total_streams: jobStatus.total_streams,
        streams_per_pipeline: jobStatus.streams_per_pipeline,
        video_output_paths: jobStatus.video_output_paths,
      });
      if (
        testStartTimestamp &&
        densityJobId &&
        metricsFrozenForJobId !== densityJobId
      ) {
        setMetricHistorySnapshot(
          history.filter((point) => point.timestamp >= testStartTimestamp),
        );
        setMetricsFrozenForJobId(densityJobId);
        setFrozenPerStreamFps(jobStatus.per_stream_fps ?? null);
      }
      setErrorMessage(null);
      setDensityJobId(null);
    } else if (jobStatus?.state === "ERROR") {
      console.error("Test failed:", jobStatus.error_message);
      setErrorMessage(jobStatus.error_message || "Test failed");
      setTestResult(null);
      setDensityJobId(null);
    } else if (jobStatus?.state === "ABORTED") {
      // Test was stopped - always freeze metrics
      if (
        testStartTimestamp &&
        densityJobId &&
        metricsFrozenForJobId !== densityJobId
      ) {
        setMetricHistorySnapshot(
          history.filter((point) => point.timestamp >= testStartTimestamp),
        );
        setMetricsFrozenForJobId(densityJobId);
        setFrozenPerStreamFps(jobStatus.per_stream_fps ?? null);
      }

      // Show results if available
      if (jobStatus.per_stream_fps || jobStatus.total_streams) {
        setTestResult({
          per_stream_fps: jobStatus.per_stream_fps,
          total_streams: jobStatus.total_streams,
          streams_per_pipeline: jobStatus.streams_per_pipeline,
          video_output_paths: jobStatus.video_output_paths,
        });
      } else {
        setTestResult(null);
      }
      setErrorMessage(null);
      setDensityJobId(null);
    }
  }, [
    jobStatus,
    history,
    testStartTimestamp,
    densityJobId,
    metricsFrozenForJobId,
  ]);

  useEffect(() => {
    if (!performanceJobStatus || performanceJobStatus.id !== performanceJobId) {
      return;
    }

    // Update live stream URLs during RUNNING state for live preview
    if (performanceJobStatus?.state === "RUNNING") {
      setPerformanceResult((prev) => ({
        total_fps: prev?.total_fps ?? null,
        per_stream_fps: prev?.per_stream_fps ?? null,
        video_output_paths: prev?.video_output_paths ?? null,
        live_stream_urls: performanceJobStatus.live_stream_urls,
      }));
    } else if (performanceJobStatus?.state === "COMPLETED") {
      setPerformanceResult({
        total_fps: performanceJobStatus.total_fps,
        per_stream_fps: performanceJobStatus.per_stream_fps,
        video_output_paths: performanceJobStatus.video_output_paths,
        live_stream_urls: performanceJobStatus.live_stream_urls,
      });
      if (
        testStartTimestamp &&
        performanceJobId &&
        metricsFrozenForJobId !== performanceJobId
      ) {
        setMetricHistorySnapshot(
          history.filter((point) => point.timestamp >= testStartTimestamp),
        );
        setMetricsFrozenForJobId(performanceJobId);
        setFrozenPerStreamFps(
          performanceJobStatus.total_fps ??
            performanceJobStatus.per_stream_fps ??
            null,
        );
      }
      setPerformanceErrorMessage(null);
      setPerformanceJobId(null);
    } else if (performanceJobStatus?.state === "ERROR") {
      console.error(
        "Throughput test failed:",
        performanceJobStatus.error_message,
      );
      setPerformanceErrorMessage(
        performanceJobStatus.error_message || "Test failed",
      );
      setPerformanceResult(null);
      setPerformanceJobId(null);
    } else if (performanceJobStatus?.state === "ABORTED") {
      // Test was stopped - always freeze metrics
      if (
        testStartTimestamp &&
        performanceJobId &&
        metricsFrozenForJobId !== performanceJobId
      ) {
        setMetricHistorySnapshot(
          history.filter((point) => point.timestamp >= testStartTimestamp),
        );
        setMetricsFrozenForJobId(performanceJobId);
        setFrozenPerStreamFps(
          performanceJobStatus.total_fps ??
            performanceJobStatus.per_stream_fps ??
            null,
        );
      }

      // Show results if available
      if (
        performanceJobStatus.total_fps ||
        performanceJobStatus.per_stream_fps
      ) {
        setPerformanceResult({
          total_fps: performanceJobStatus.total_fps,
          per_stream_fps: performanceJobStatus.per_stream_fps,
          video_output_paths: performanceJobStatus.video_output_paths,
          live_stream_urls: performanceJobStatus.live_stream_urls,
        });
      } else {
        setPerformanceResult(null);
      }
      setPerformanceErrorMessage(null);
      setPerformanceJobId(null);
    }
  }, [
    performanceJobStatus,
    history,
    testStartTimestamp,
    performanceJobId,
    metricsFrozenForJobId,
  ]);

  useEffect(() => {
    if (pipelines.length > 0 && pipelineSelections.length === 0) {
      setPipelineSelections([
        {
          pipelineId: pipelines[0].id,
          stream_rate: 100,
        },
      ]);
    }
  }, [pipelines, pipelineSelections.length]);

  useEffect(() => {
    // Reset carousel index when pipeline selections change
    setCarouselIndex(0);
  }, [pipelineSelections.length]);

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
          next[selection.pipelineId] = 1;
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

  useEffect(() => {
    if (pipelineSelections.length === 0) return;

    setSelectedVariantByPipelineId((prev) => {
      const next = { ...prev };
      let changed = false;
      const validIds = new Set(
        pipelineSelections.map((selection) => selection.pipelineId),
      );

      pipelineSelections.forEach((selection) => {
        const pipeline = pipelines.find((p) => p.id === selection.pipelineId);
        const fallbackVariantId = pipeline?.variants?.[0]?.id;
        if (!pipeline || !fallbackVariantId) return;

        const currentVariantId = next[selection.pipelineId];
        const hasCurrentVariant =
          !!currentVariantId &&
          pipeline.variants.some((variant) => variant.id === currentVariantId);

        if (!hasCurrentVariant) {
          next[selection.pipelineId] = fallbackVariantId;
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
  }, [pipelineSelections, pipelines]);

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
    setTestStartTimestamp(Date.now());
    setMetricHistorySnapshot([]);
    setMetricsFrozenForJobId(null);
    setFrozenPerStreamFps(null);
    setLastRunTest(activeTest);
    setPreviewCarouselIndex(0);

    // Prepare pipeline graphs with applied edits
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

    const getPipelineVariantForRun = (pipelineId: string) =>
      getSelectedVariantForPipeline(pipelineId);

    const preparePipelineGraph = (pipelineId: string) => {
      const pipeline = pipelines.find((p) => p.id === pipelineId);
      const variant = getPipelineVariantForRun(pipelineId);
      if (!pipeline || !variant?.pipeline_graph) return null;

      const updatedNodes = variant.pipeline_graph.nodes.map((node) => {
        const edits =
          nodeDataEdits[getNodeEditKey(pipeline.id, variant.id, node.id)];
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

        const sanitizedData = sanitizeNodeData(node.type, mergedData);

        const normalizedData = Object.fromEntries(
          Object.entries(sanitizedData)
            .filter(
              ([key]) => !(node.type === "gvametaconvert" && key === "device"),
            )
            .map(([key, value]) => [
              key,
              value === null || value === undefined ? "" : String(value),
            ]),
        ) as { [key: string]: string };

        return {
          ...node,
          data: normalizedData,
        };
      });

      return {
        nodes: updatedNodes,
        edges: variant.pipeline_graph.edges ?? [],
      };
    };

    if (activeTest === "performance-test") {
      setPerformanceResult(null);
      setPerformanceErrorMessage(null);
      try {
        const outputMode = performanceLivePreviewEnabled
          ? "live_stream"
          : "disabled";

        const maxRuntime = 1800;

        const result = await runPerformanceTest({
          performanceTestSpec: {
            execution_config: {
              output_mode: outputMode,
              max_runtime: maxRuntime,
            },
            pipeline_performance_specs: pipelineSelections.map((selection) => {
              const variant = getPipelineVariantForRun(selection.pipelineId);
              const pipelineGraph = preparePipelineGraph(selection.pipelineId);

              return {
                pipeline: pipelineGraph
                  ? {
                      source: "graph" as const,
                      pipeline_id: selection.pipelineId,
                      variant_id: variant?.id ?? "",
                      pipeline_graph: pipelineGraph,
                    }
                  : {
                      source: "variant" as const,
                      pipeline_id: selection.pipelineId,
                      variant_id: variant?.id ?? "",
                    },
                streams: performanceStreams[selection.pipelineId] ?? 1,
              };
            }),
          },
        }).unwrap();
        setPerformanceJobId(result.job_id);
      } catch (err) {
        console.error("Failed to run throughput test:", err);
      }
      return;
    }

    setTestResult(null);
    setErrorMessage(null);
    try {
      const result = await runDensityTest({
        densityTestSpec: {
          execution_config: {
            output_mode: "disabled",
            max_runtime: 10,
          },
          fps_floor: fpsFloor,
          pipeline_density_specs: pipelineSelections.map((selection) => {
            const variant = getPipelineVariantForRun(selection.pipelineId);
            const pipelineGraph = preparePipelineGraph(selection.pipelineId);

            return {
              pipeline: pipelineGraph
                ? {
                    source: "graph" as const,
                    pipeline_id: selection.pipelineId,
                    variant_id: variant?.id ?? "",
                    pipeline_graph: pipelineGraph,
                  }
                : {
                    source: "variant" as const,
                    pipeline_id: selection.pipelineId,
                    variant_id: variant?.id ?? "",
                  },
              stream_rate: selection.stream_rate,
            };
          }),
        },
      }).unwrap();
      setDensityJobId(result.job_id);
    } catch (err) {
      console.error("Failed to run density test:", err);
    }
  };

  const handleStopTest = async () => {
    try {
      if (activeTest === "performance-test" && performanceJobId) {
        await stopPerformanceTestJob({ jobId: performanceJobId }).unwrap();
        // Don't set jobId to null - let polling continue to get ABORTED status
      } else if (activeTest === "density-test" && densityJobId) {
        await stopDensityTestJob({ jobId: densityJobId }).unwrap();
        // Don't set jobId to null - let polling continue to get ABORTED status
      }
    } catch (err) {
      console.error("Failed to stop test:", err);
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
      <div className="relative z-10 h-full flex flex-col bg-slate-950/80 min-h-0">
        {demoStep === "selection" && (
          /* HEADER - Only for selection step */
          <div className="h-[70px] px-4 flex items-center justify-between border-b border-slate-300/20 backdrop-blur-md shadow-lg">
            <h1 className={`text-xl font-bold ${colors.headerTitle}`}>
              Intel® Visual Pipeline and Platform Evaluation Tool (ViPPET)
            </h1>
            <div className="flex items-center gap-3">
              <button
                onClick={() => navigate("/")}
                className={`group relative px-6 py-3 rounded-xl border bg-slate-800/50 backdrop-blur-xl transition-all duration-100 ${colors.exitButton}`}
              >
                <div className="flex items-center gap-2">
                  <Home
                    className={`w-5 h-5 group-hover:scale-110 transition-transform ${colors.exitIcon}`}
                  />
                  <span
                    className={`text-base font-semibold ${colors.exitIcon}`}
                  >
                    Exit
                  </span>
                </div>
              </button>
            </div>
          </div>
        )}
        {/* MAIN CONTENT */}
        <div
          className={`relative z-10 p-3 ${demoStep === "selection" ? "h-[calc(100vh-70px)]" : "flex-1"} min-h-0`}
        >
          {demoStep === "selection" ? (
            /* PIPELINE SELECTION VIEW */
            <div className="h-full flex flex-col animate-[slideUp_0.35s_ease-out]">
              {/* Pipeline Cards Grid */}
              <div className="flex-1 overflow-auto p-6 pt-8">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 mt-20">
                  {groupedPipelines
                    .filter((group) => {
                      const allowedPipelineNames = [
                        "Goods Detection",
                        "License Plate Recognition",
                        "Simple NVR",
                        "Smart NVR",
                      ];
                      return allowedPipelineNames.includes(group.baseName);
                    })
                    .map((group) => {
                      const isSelected = selectedModels.has(group.baseName);
                      const availableDevices = Object.keys(group.pipelines);

                      return (
                        <Card
                          key={group.id}
                          onClick={() => {
                            const newSelected = new Map(selectedModels);
                            if (isSelected) {
                              newSelected.delete(group.baseName);
                            } else {
                              const firstDevice = availableDevices[0];
                              if (firstDevice) {
                                newSelected.set(
                                  group.baseName,
                                  group.pipelines[firstDevice].id,
                                );
                              }
                            }
                            setSelectedModels(newSelected);
                          }}
                          className={`relative flex flex-col transition-all duration-100 overflow-hidden border-2 bg-gradient-to-br from-slate-900/90 via-slate-800/70 to-slate-900/90 backdrop-blur-md cursor-pointer scale-[0.9] ${
                            isSelected
                              ? "border-blue-500 shadow-lg shadow-blue-500/50 scale-[0.95]"
                              : "border-slate-400/30 hover:border-blue-500/50 hover:shadow-lg hover:scale-[0.95]"
                          }`}
                        >
                          <CardHeader className="flex-1">
                            <div className="absolute right-3 top-3">
                              <Checkbox
                                checked={isSelected}
                                onCheckedChange={(checked) => {
                                  const newSelected = new Map(selectedModels);
                                  if (checked) {
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
                            </div>
                            <CardTitle className="min-h-8 text-slate-200">
                              {group.baseName}
                            </CardTitle>
                            <img
                              src={
                                Object.values(group.pipelines)[0]?.thumbnail ||
                                thumbnailPlaceholder
                              }
                              alt={group.baseName}
                              className="w-full h-auto rounded-md"
                            />
                            <CardDescription className="line-clamp-4 min-h-18 text-slate-400">
                              {group.description}
                            </CardDescription>
                          </CardHeader>
                          <div className="px-6 pb-4"></div>
                        </Card>
                      );
                    })}
                </div>
              </div>

              {/* Next Button */}
              <div className="relative flex items-center justify-end gap-3 p-3 pt-5">
                <div className="absolute inset-x-0 flex justify-center">
                  <span className="text-lg font-bold text-blue-200">
                    Selected pipelines: {selectedModels.size}
                  </span>
                </div>
                <button
                  onClick={() => {
                    if (selectedModels.size > 0) {
                      // Initialize pipeline selections with selected pipelines
                      const pipelineIds = Array.from(selectedModels.values());
                      const count = pipelineIds.length;
                      const baseRate = Math.floor(100 / count);
                      const remainder = 100 - baseRate * count;

                      const selections = pipelineIds.map((id, index) => ({
                        pipelineId: id,
                        stream_rate:
                          index === 0 ? baseRate + remainder : baseRate,
                      }));
                      setPipelineSelections(selections);
                      // Set first pipeline as selected for configuration
                      setSelectedConfigPipelineId(selections[0].pipelineId);
                      setDemoStep("configuration");
                    }
                  }}
                  disabled={selectedModels.size === 0}
                  className="group relative px-6 py-3 rounded-xl bg-gradient-to-r from-blue-600 to-blue-500 hover:scale-[1.04] hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-100"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-base font-semibold text-white">
                      Next
                    </span>
                    <ChevronRight className="w-5 h-5 text-white group-hover:scale-110 transition-transform" />
                  </div>
                </button>
              </div>
            </div>
          ) : demoStep === "configuration" ? (
            (() => {
              const cardsPerPage = 4;
              const totalPages = Math.ceil(
                pipelineSelections.length / cardsPerPage,
              );
              const startIdx = carouselIndex * cardsPerPage;
              const endIdx = startIdx + cardsPerPage;
              const visiblePipelines = pipelineSelections.slice(
                startIdx,
                endIdx,
              );

              const pipelineCardsSection = (
                <div className="relative h-[215px]">
                  <div className="grid grid-cols-4 gap-2 h-full">
                    {visiblePipelines.map((selection) => {
                      const pipeline = pipelines.find(
                        (p) => p.id === selection.pipelineId,
                      );
                      if (!pipeline) return null;
                      const isSelected =
                        selectedConfigPipelineId === selection.pipelineId;

                      return (
                        <Card
                          key={selection.pipelineId}
                          onClick={() =>
                            setSelectedConfigPipelineId(selection.pipelineId)
                          }
                          className={`relative flex w-full max-h-[215px] flex-col border bg-gradient-to-br from-slate-800/90 via-slate-750/80 to-slate-800/90 backdrop-blur-md overflow-hidden shadow-lg hover:shadow-xl transition-all cursor-pointer ${
                            isSelected
                              ? "border-blue-500 ring-2 ring-blue-500/50"
                              : "border-slate-400/40 hover:border-blue-500/60 opacity-50 grayscale"
                          } ${isReadOnly ? "opacity-70" : ""}`}
                        >
                          <CardHeader className="pl-2 pr-2 pt-0 pb-0 -mt-2">
                            <CardTitle className="text-[10px] text-slate-200 leading-tight text-center font-semibold line-clamp-2 min-h-[3rem]">
                              {getBasePipelineName(pipeline.name)}
                            </CardTitle>
                          </CardHeader>
                          <div className="p-0 pb-0 -mt-10">
                            <img
                              src={pipeline.thumbnail || thumbnailPlaceholder}
                              alt={pipeline.name}
                              className="w-full max-w-[110px] aspect-[4/3] object-cover rounded-md mx-auto"
                            />
                          </div>
                          <div className="mt-auto px-1 pb-0">
                            <p className="ml-3 -mt-2 mb-1 text-[8px] font-semibold uppercase tracking-wide text-slate-400">
                              Best known configurations
                            </p>
                            <select
                              value={
                                getSelectedVariantForPipeline(
                                  selection.pipelineId,
                                )?.id ?? ""
                              }
                              onChange={(e) =>
                                setSelectedVariantByPipelineId((prev) => {
                                  const nextVariantId = e.target.value;

                                  return {
                                    ...prev,
                                    [selection.pipelineId]: nextVariantId,
                                  };
                                })
                              }
                              onClick={(e) => e.stopPropagation()}
                              disabled={
                                isReadOnly || pipeline.variants.length < 1
                              }
                              className={`block w-[92%] mx-auto px-2 py-1 bg-slate-900/90 border border-slate-400/40 rounded text-slate-200 text-[10px] focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 ${isReadOnly ? "opacity-60 cursor-not-allowed" : ""}`}
                            >
                              {pipeline.variants.map((variant) => (
                                <option key={variant.id} value={variant.id}>
                                  {formatVariantDisplayName(
                                    variant.name,
                                    variant.id,
                                  )}
                                </option>
                              ))}
                            </select>
                          </div>
                        </Card>
                      );
                    })}
                  </div>

                  {/* Carousel navigation buttons */}
                  {totalPages > 1 && (
                    <>
                      <button
                        onClick={() =>
                          setCarouselIndex((prev) => Math.max(0, prev - 1))
                        }
                        disabled={carouselIndex === 0}
                        className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-3 bg-slate-800/90 hover:bg-slate-700/90 disabled:opacity-30 disabled:cursor-not-allowed rounded-full p-2 shadow-lg backdrop-blur-sm border border-slate-600/50 transition-all"
                      >
                        <ChevronLeft className="w-5 h-5 text-slate-200" />
                      </button>
                      <button
                        onClick={() =>
                          setCarouselIndex((prev) =>
                            Math.min(totalPages - 1, prev + 1),
                          )
                        }
                        disabled={carouselIndex >= totalPages - 1}
                        className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-3 bg-slate-800/90 hover:bg-slate-700/90 disabled:opacity-30 disabled:cursor-not-allowed rounded-full p-2 shadow-lg backdrop-blur-sm border border-slate-600/50 transition-all"
                      >
                        <ChevronRight className="w-5 h-5 text-slate-200" />
                      </button>

                      {/* Dots indicator */}
                      <div className="absolute -bottom-4 left-1/2 -translate-x-1/2 flex gap-1.5">
                        {Array.from({ length: totalPages }).map((_, idx) => (
                          <button
                            key={idx}
                            onClick={() => setCarouselIndex(idx)}
                            className={`w-2 h-2 rounded-full transition-all ${
                              idx === carouselIndex
                                ? "bg-blue-500 w-6"
                                : "bg-slate-600 hover:bg-slate-500"
                            }`}
                          />
                        ))}
                      </div>
                    </>
                  )}
                </div>
              );

              const livePreviewContent =
                performanceJobId &&
                performanceResult?.live_stream_urls &&
                Object.keys(performanceResult.live_stream_urls).length > 0
                  ? (() => {
                      const previewsPerPage = 2;
                      const totalPreviewPages = Math.ceil(
                        pipelineSelections.length / previewsPerPage,
                      );
                      const startIdx = previewCarouselIndex * previewsPerPage;
                      const endIdx = startIdx + previewsPerPage;
                      const visiblePreviews = pipelineSelections.slice(
                        startIdx,
                        endIdx,
                      );

                      return (
                        <div className="relative rounded-lg border border-slate-400/30 p-3 bg-slate-950/30 mb-3">
                          <div className="grid grid-cols-2 gap-3 min-h-[280px]">
                            {visiblePreviews.map((selection, localIdx) => {
                              const pipeline = pipelines.find(
                                (p) => p.id === selection.pipelineId,
                              );
                              const globalIdx = startIdx + localIdx;
                              const streamSpec =
                                performanceJobStatus?.streams_per_pipeline?.[
                                  globalIdx
                                ];
                              const streamUrl = streamSpec?.id
                                ? performanceResult?.live_stream_urls?.[
                                    streamSpec.id
                                  ]
                                : null;

                              return (
                                <div
                                  key={selection.pipelineId}
                                  className="border border-slate-400/30 rounded-lg p-2 bg-slate-950/40 flex flex-col"
                                >
                                  <p className="text-xs font-semibold text-slate-300 mb-2 truncate">
                                    {`${pipeline?.name || "Unknown Pipeline"} • LIVE PREVIEW`}
                                  </p>
                                  <div className="flex-1 flex items-center justify-center bg-black/20 rounded overflow-hidden min-h-[220px]">
                                    <div className="w-full h-full">
                                      {streamUrl ? (
                                        <WebRTCVideoPlayer
                                          streamUrl={streamUrl}
                                        />
                                      ) : (
                                        <div className="flex items-center justify-center h-full text-slate-400 text-sm">
                                          Waiting for stream...
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>

                          {totalPreviewPages > 1 && (
                            <>
                              <button
                                onClick={() =>
                                  setPreviewCarouselIndex((prev) =>
                                    Math.max(0, prev - 1),
                                  )
                                }
                                disabled={previewCarouselIndex === 0}
                                className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-3 bg-slate-800/90 hover:bg-slate-700/90 disabled:opacity-30 disabled:cursor-not-allowed rounded-full p-2 shadow-lg backdrop-blur-sm border border-slate-600/50 transition-all z-10"
                              >
                                <ChevronLeft className="w-5 h-5 text-slate-200" />
                              </button>
                              <button
                                onClick={() =>
                                  setPreviewCarouselIndex((prev) =>
                                    Math.min(totalPreviewPages - 1, prev + 1),
                                  )
                                }
                                disabled={
                                  previewCarouselIndex >= totalPreviewPages - 1
                                }
                                className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-3 bg-slate-800/90 hover:bg-slate-700/90 disabled:opacity-30 disabled:cursor-not-allowed rounded-full p-2 shadow-lg backdrop-blur-sm border border-slate-600/50 transition-all z-10"
                              >
                                <ChevronRight className="w-5 h-5 text-slate-200" />
                              </button>

                              <div className="absolute -bottom-4 left-1/2 -translate-x-1/2 flex gap-1.5">
                                {Array.from({ length: totalPreviewPages }).map(
                                  (_, idx) => (
                                    <button
                                      key={idx}
                                      onClick={() =>
                                        setPreviewCarouselIndex(idx)
                                      }
                                      className={`w-2 h-2 rounded-full transition-all ${
                                        idx === previewCarouselIndex
                                          ? "bg-blue-500 w-6"
                                          : "bg-slate-600 hover:bg-slate-500"
                                      }`}
                                    />
                                  ),
                                )}
                              </div>
                            </>
                          )}
                        </div>
                      );
                    })()
                  : null;

              const pipelineConfigSection = (
                <div
                  className={`rounded-xl bg-gradient-to-br from-slate-900/90 via-slate-800/70 to-slate-900/90 border p-4 backdrop-blur-md flex flex-col min-h-0 h-full mt-2 ${pipelineConfigContainerMaxHeightClass} overflow-hidden ${colors.testBorder}`}
                >
                  <Accordion
                    type="single"
                    collapsible
                    value={openConfigSection}
                    onValueChange={(value) =>
                      setOpenConfigSection((prev) => {
                        if (value) return value;
                        return prev === "pipeline-config"
                          ? "run-config"
                          : "pipeline-config";
                      })
                    }
                    className="w-full space-y-3"
                  >
                    <AccordionItem
                      value="pipeline-config"
                      className="border border-slate-400/30 rounded-lg bg-slate-950/60"
                    >
                      <AccordionTrigger className="px-4 py-6 hover:no-underline">
                        <span
                          className={`text-sm uppercase font-bold tracking-wider ${colors.testTitle}`}
                        >
                          Pipeline Configuration
                        </span>
                      </AccordionTrigger>
                      <AccordionContent
                        className={`px-3 pb-3 ${pipelineConfigMaxHeightClass} overflow-y-auto scroll-smooth`}
                        onWheel={handleFastScroll}
                      >
                        <div className="pr-1 min-h-[20vh]">
                          <div className="flex-1 min-h-0 flex flex-col">
                            {selectedConfigPipelineId ? (
                              (() => {
                                const pipeline = pipelines.find(
                                  (p) => p.id === selectedConfigPipelineId,
                                );
                                const selectedVariant = pipeline
                                  ? getSelectedVariantForPipeline(pipeline.id)
                                  : null;
                                if (!pipeline || !selectedVariant) return null;

                                return (
                                  <>
                                    <div className="flex-1 min-h-0 overflow-y-auto pr-1 pb-4">
                                      <Accordion
                                        key={selectedVariant.id}
                                        type="single"
                                        collapsible
                                        className="w-full space-y-2"
                                      >
                                        {selectedVariant.pipeline_graph?.nodes
                                          ?.filter((node) => {
                                            const nodeTag =
                                              nodeTypeToTag[node.type] || null;
                                            const hiddenTags = [
                                              "Counter",
                                              "Converter",
                                              "Splitter",
                                              "Sink",
                                            ];
                                            return !hiddenTags.includes(
                                              nodeTag ?? "",
                                            );
                                          })
                                          .map((node) => {
                                            const nodeTag =
                                              nodeTypeToTag[node.type] || null;
                                            const displayTag =
                                              nodeTag === "Muxer"
                                                ? "Storage output"
                                                : nodeTag === "Publisher"
                                                  ? "Metadata output"
                                                  : nodeTag;
                                            const nodeConfig = getNodeConfig(
                                              node.type,
                                            );
                                            const editableProperties =
                                              nodeConfig?.editableProperties ??
                                              [];

                                            const dataEntries = nodeConfig
                                              ? editableProperties
                                                  .filter(
                                                    (prop) =>
                                                      prop.key !== "device",
                                                  )
                                                  .map((prop) => [
                                                    prop.key,
                                                    node.data[prop.key] ??
                                                      prop.defaultValue,
                                                    prop,
                                                  ])
                                              : Object.entries(node.data ?? {})
                                                  .filter(
                                                    ([key]) =>
                                                      key !== "device" &&
                                                      !["label"].includes(
                                                        key,
                                                      ) &&
                                                      !key.startsWith("__"),
                                                  )
                                                  .map(([key, value]) => [
                                                    key,
                                                    value,
                                                    null,
                                                  ]);

                                            const getEditedValue = (
                                              nodeId: string,
                                              key: string,
                                              originalValue: unknown,
                                            ) => {
                                              return (
                                                nodeDataEdits[
                                                  getNodeEditKey(
                                                    pipeline.id,
                                                    selectedVariant.id,
                                                    nodeId,
                                                  )
                                                ]?.[key] ?? originalValue
                                              );
                                            };

                                            const handleValueChange = (
                                              nodeId: string,
                                              key: string,
                                              value: unknown,
                                            ) => {
                                              const editKey = getNodeEditKey(
                                                pipeline.id,
                                                selectedVariant.id,
                                                nodeId,
                                              );
                                              setNodeDataEdits((prev) => {
                                                const nextEntry = {
                                                  ...prev[editKey],
                                                  [key]: value,
                                                };

                                                if (
                                                  key === "inference-region" &&
                                                  String(value) !== "roi-list"
                                                ) {
                                                  nextEntry["object-class"] =
                                                    "";
                                                }

                                                return {
                                                  ...prev,
                                                  [editKey]: nextEntry,
                                                };
                                              });
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
                                                    {displayTag ? (
                                                      <>
                                                        <span className="font-medium text-white">
                                                          {displayTag}
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
                                                      ([
                                                        key,
                                                        value,
                                                        propConfig,
                                                      ]) => {
                                                        const currentValue =
                                                          getEditedValue(
                                                            node.id,
                                                            String(key),
                                                            value,
                                                          );
                                                        const config =
                                                          propConfig as NodePropertyConfig | null;
                                                        const isSourceLocationField =
                                                          nodeTypeToTag[
                                                            node.type
                                                          ] === "Source" &&
                                                          String(key) ===
                                                            "location";

                                                        const inferenceRegionValue =
                                                          getEditedValue(
                                                            node.id,
                                                            "inference-region",
                                                            node.data?.[
                                                              "inference-region"
                                                            ],
                                                          );
                                                        const isRoiRegion =
                                                          String(
                                                            inferenceRegionValue ??
                                                              "",
                                                          ) === "roi-list";

                                                        return (
                                                          <div
                                                            key={String(key)}
                                                            className="space-y-1"
                                                          >
                                                            <label className="text-xs font-medium text-slate-300 block">
                                                              {config?.label ??
                                                                String(key)}
                                                            </label>
                                                            {String(key) ===
                                                            "model" ? (
                                                              <select
                                                                value={String(
                                                                  currentValue ??
                                                                    "",
                                                                )}
                                                                onChange={(e) =>
                                                                  handleValueChange(
                                                                    node.id,
                                                                    String(key),
                                                                    e.target
                                                                      .value,
                                                                  )
                                                                }
                                                                disabled={
                                                                  isReadOnly
                                                                }
                                                                className={`w-full px-2 py-1.5 bg-slate-900/90 border border-slate-400/40 rounded text-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 ${isReadOnly ? "opacity-60 cursor-not-allowed" : ""}`}
                                                              >
                                                                <option value="">
                                                                  Select{" "}
                                                                  {
                                                                    config?.label
                                                                  }
                                                                </option>
                                                                {models
                                                                  .filter(
                                                                    (model) =>
                                                                      model.category ===
                                                                      config
                                                                        ?.params
                                                                        ?.filter,
                                                                  )
                                                                  .map(
                                                                    (model) => (
                                                                      <option
                                                                        key={
                                                                          model.name
                                                                        }
                                                                        value={
                                                                          model.display_name ??
                                                                          model.name
                                                                        }
                                                                      >
                                                                        {model.display_name ??
                                                                          model.name}
                                                                      </option>
                                                                    ),
                                                                  )}
                                                              </select>
                                                            ) : isSourceLocationField &&
                                                              videoFilenames.length >
                                                                0 ? (
                                                              <select
                                                                value={getFilenameFromPath(
                                                                  currentValue,
                                                                )}
                                                                onChange={(e) =>
                                                                  handleValueChange(
                                                                    node.id,
                                                                    String(key),
                                                                    e.target
                                                                      .value,
                                                                  )
                                                                }
                                                                disabled={
                                                                  isReadOnly
                                                                }
                                                                className={`w-full px-2 py-1.5 bg-slate-900/90 border border-slate-400/40 rounded text-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 ${isReadOnly ? "opacity-60 cursor-not-allowed" : ""}`}
                                                              >
                                                                <option value="">
                                                                  Select
                                                                  filename
                                                                </option>
                                                                {videoFilenames.map(
                                                                  (
                                                                    filename,
                                                                  ) => (
                                                                    <option
                                                                      key={
                                                                        filename
                                                                      }
                                                                      value={
                                                                        filename
                                                                      }
                                                                    >
                                                                      {filename}
                                                                    </option>
                                                                  ),
                                                                )}
                                                              </select>
                                                            ) : config?.type ===
                                                              "select" ? (
                                                              <select
                                                                value={String(
                                                                  currentValue ??
                                                                    "",
                                                                )}
                                                                onChange={(e) =>
                                                                  handleValueChange(
                                                                    node.id,
                                                                    String(key),
                                                                    e.target
                                                                      .value,
                                                                  )
                                                                }
                                                                disabled={
                                                                  isReadOnly
                                                                }
                                                                className={`w-full px-2 py-1.5 bg-slate-900/90 border border-slate-400/40 rounded text-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 ${isReadOnly ? "opacity-60 cursor-not-allowed" : ""}`}
                                                              >
                                                                {config.options?.map(
                                                                  (option) => (
                                                                    <option
                                                                      key={
                                                                        option
                                                                      }
                                                                      value={
                                                                        option
                                                                      }
                                                                    >
                                                                      {option}
                                                                    </option>
                                                                  ),
                                                                )}
                                                              </select>
                                                            ) : String(key) ===
                                                              "object-class" ? (
                                                              <input
                                                                type="text"
                                                                value={String(
                                                                  currentValue ??
                                                                    "",
                                                                )}
                                                                onChange={(e) =>
                                                                  handleValueChange(
                                                                    node.id,
                                                                    String(key),
                                                                    e.target
                                                                      .value,
                                                                  )
                                                                }
                                                                disabled={
                                                                  isReadOnly ||
                                                                  !isRoiRegion
                                                                }
                                                                className={`w-full px-2 py-1.5 bg-slate-900/90 border border-slate-400/40 rounded text-slate-200 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 ${isReadOnly || !isRoiRegion ? "opacity-60 cursor-not-allowed" : ""}`}
                                                                placeholder={
                                                                  !isRoiRegion
                                                                    ? "Disabled unless roi-list"
                                                                    : (config?.description ??
                                                                      "Enter value")
                                                                }
                                                              />
                                                            ) : config?.type ===
                                                              "boolean" ? (
                                                              <div className="flex items-center gap-2">
                                                                <Checkbox
                                                                  checked={
                                                                    currentValue ===
                                                                      true ||
                                                                    currentValue ===
                                                                      "true"
                                                                  }
                                                                  onCheckedChange={(
                                                                    checked,
                                                                  ) =>
                                                                    handleValueChange(
                                                                      node.id,
                                                                      String(
                                                                        key,
                                                                      ),
                                                                      checked,
                                                                    )
                                                                  }
                                                                  disabled={
                                                                    isReadOnly
                                                                  }
                                                                  className={
                                                                    colors.checkbox
                                                                  }
                                                                />
                                                                <span className="text-xs text-slate-400">
                                                                  {
                                                                    config.description
                                                                  }
                                                                </span>
                                                              </div>
                                                            ) : config?.type ===
                                                              "textarea" ? (
                                                              <textarea
                                                                value={String(
                                                                  currentValue ??
                                                                    "",
                                                                )}
                                                                onChange={(e) =>
                                                                  handleValueChange(
                                                                    node.id,
                                                                    String(key),
                                                                    e.target
                                                                      .value,
                                                                  )
                                                                }
                                                                disabled={
                                                                  isReadOnly
                                                                }
                                                                className={`w-full px-2 py-1.5 bg-slate-900/90 border border-slate-400/40 rounded text-slate-200 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 resize-y min-h-[60px] ${isReadOnly ? "opacity-60 cursor-not-allowed" : ""}`}
                                                                placeholder={
                                                                  config.description
                                                                }
                                                              />
                                                            ) : config?.type ===
                                                              "number" ? (
                                                              <input
                                                                type="number"
                                                                value={String(
                                                                  currentValue ??
                                                                    "",
                                                                )}
                                                                onChange={(e) =>
                                                                  handleValueChange(
                                                                    node.id,
                                                                    String(key),
                                                                    parseFloat(
                                                                      e.target
                                                                        .value,
                                                                    ),
                                                                  )
                                                                }
                                                                disabled={
                                                                  isReadOnly
                                                                }
                                                                className={`w-full px-2 py-1.5 bg-slate-900/90 border border-slate-400/40 rounded text-slate-200 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 ${isReadOnly ? "opacity-60 cursor-not-allowed" : ""}`}
                                                                placeholder={
                                                                  config.description
                                                                }
                                                              />
                                                            ) : (
                                                              <input
                                                                type="text"
                                                                value={String(
                                                                  currentValue ??
                                                                    "",
                                                                )}
                                                                onChange={(e) =>
                                                                  handleValueChange(
                                                                    node.id,
                                                                    String(key),
                                                                    e.target
                                                                      .value,
                                                                  )
                                                                }
                                                                disabled={
                                                                  isReadOnly
                                                                }
                                                                className={`w-full px-2 py-1.5 bg-slate-900/90 border border-slate-400/40 rounded text-slate-200 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 ${isReadOnly ? "opacity-60 cursor-not-allowed" : ""}`}
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
                                    </div>
                                  </>
                                );
                              })()
                            ) : (
                              <div className="flex-1 flex items-center justify-center text-slate-400">
                                <p className="text-sm">
                                  Select a pipeline to configure
                                </p>
                              </div>
                            )}
                          </div>
                        </div>
                      </AccordionContent>
                    </AccordionItem>

                    <AccordionItem
                      value="run-config"
                      className="border border-slate-400/30 rounded-lg bg-slate-950/60"
                    >
                      <AccordionTrigger className="px-4 py-6 hover:no-underline">
                        <span
                          className={`text-sm uppercase font-bold tracking-wider ${colors.testTitle}`}
                        >
                          Run Configuration
                        </span>
                      </AccordionTrigger>
                      <AccordionContent
                        className={`px-3 pb-3 ${runConfigMaxHeightClass} flex flex-col`}
                      >
                        <div
                          className="flex-1 min-h-0 overflow-y-auto scroll-smooth"
                          onWheel={handleFastScroll}
                        >
                          <div className="pr-1 pb-3">
                            <div className="w-full">
                              <div className="inline-flex rounded-lg border border-slate-400/40 bg-slate-950/70 p-1 mb-3">
                                <button
                                  type="button"
                                  onClick={() =>
                                    setActiveTest("performance-test")
                                  }
                                  disabled={isReadOnly}
                                  className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${
                                    activeTest === "performance-test"
                                      ? "bg-blue-600 text-white"
                                      : "text-slate-300 hover:text-white"
                                  } disabled:opacity-50 disabled:cursor-not-allowed`}
                                >
                                  Throughput Test
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setActiveTest("density-test")}
                                  disabled={isReadOnly}
                                  className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${
                                    activeTest === "density-test"
                                      ? "bg-blue-600 text-white"
                                      : "text-slate-300 hover:text-white"
                                  } disabled:opacity-50 disabled:cursor-not-allowed`}
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
                                                {pipeline?.name
                                                  ? getBasePipelineName(
                                                      pipeline.name,
                                                    )
                                                  : "Pipeline"}
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
                                              disabled={isReadOnly}
                                            />
                                          </div>
                                        );
                                      })}
                                    </div>

                                    {/* Live Preview */}
                                    <div className="flex flex-col gap-2">
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
                                          disabled={isReadOnly}
                                          className={colors.checkbox}
                                        />
                                        <div className="flex items-center gap-1.5">
                                          <label className="text-xs text-slate-300 py-5">
                                            Show live preview
                                          </label>
                                          <CheckboxInfoHint description="Shows pipeline output in real time while it is running." />
                                        </div>
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
                                                {pipeline?.name
                                                  ? getBasePipelineName(
                                                      pipeline.name,
                                                    )
                                                  : "Pipeline"}
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
                                              disabled={isReadOnly}
                                            />
                                          </div>
                                        );
                                      })}
                                    </div>

                                    {/* FPS Floor */}
                                    <div className="flex gap-6">
                                      <div className="space-y-2 py-2">
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
                                          disabled={isReadOnly}
                                          className={`w-28 px-2 py-1.5 bg-slate-900/90 border border-slate-400/40 rounded text-slate-200 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 no-spin ${isReadOnly ? "opacity-60 cursor-not-allowed" : ""}`}
                                          placeholder="Minimum FPS threshold"
                                          min={0}
                                        />
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  </Accordion>
                </div>
              );

              const actionButtonsSection = (
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setDemoStep("selection")}
                    className={`group relative px-6 py-2.5 rounded-xl border bg-slate-800/50 backdrop-blur-xl transition-all duration-100 ${colors.exitButton}`}
                  >
                    <span
                      className={`text-base font-semibold ${colors.exitIcon}`}
                    >
                      Back
                    </span>
                  </button>
                  <button
                    onClick={isRunDisabled ? handleStopTest : handleRunTest}
                    className={`flex-1 relative px-4 py-2.5 text-white rounded-lg font-bold tracking-wider text-sm shadow-lg transition-all duration-100 ${colors.runButton}`}
                  >
                    <div
                      className={`absolute inset-0 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-100 ${colors.runButtonOverlay}`}
                    ></div>
                    <span className="relative">
                      {isRunDisabled ? "Stop" : "Run Test"}
                    </span>
                  </button>
                </div>
              );

              const resultsSection = showResultsPanel ? (
                <div
                  className={`rounded-xl bg-gradient-to-br from-slate-900/90 via-slate-800/70 to-slate-900/90 border p-4 backdrop-blur-md flex flex-col flex-1 min-h-0 ${colors.gridResultsBorder} animate-[softSlideInRight_0.9s_ease-out] ${isTestFinished ? "ring-1 ring-blue-400/30 shadow-[0_0_20px_rgba(59,130,246,0.15)]" : ""}`}
                >
                  <div className="mb-3 flex-shrink-0">
                    <p
                      className={`text-sm uppercase font-bold tracking-wider ${colors.gridResultsTitle}`}
                    >
                      {lastRunTest === "performance-test" &&
                      performanceJobStatus?.state === "RUNNING"
                        ? "Test Status: RUNNING"
                        : lastRunTest === "density-test" &&
                            jobStatus?.state === "RUNNING"
                          ? "Test Status: RUNNING"
                          : "Test Summary"}
                    </p>
                    {lastRunTest === "performance-test" &&
                      performanceJobStatus?.state === "RUNNING" && (
                        <div className="mt-1 flex items-center gap-2">
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
                          <p className="text-xs text-neutral-300">
                            Running throughput test...
                          </p>
                        </div>
                      )}
                  </div>

                  <div className="flex-1 min-h-0 overflow-y-auto pr-2">
                    {lastRunTest === "performance-test" ? (
                      <div className="space-y-3">
                        {livePreviewContent}

                        {performanceJobId && performanceJobStatus && (
                          <div className="space-y-2">
                            {performanceJobStatus.state === "RUNNING" && (
                              <div>
                                <TestProgressIndicator
                                  key={performanceJobId || testStartTimestamp}
                                  forceDark={true}
                                  useDemoStyles={true}
                                />
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
                          !performanceErrorMessage &&
                          !hasFrozenMetrics && (
                            <div className="flex items-center justify-center h-full text-slate-400">
                              <p className="text-sm">
                                Results will appear here after running the test
                              </p>
                            </div>
                          )}

                        {!performanceResult &&
                          hasFrozenMetrics &&
                          frozenMetricsSummary && (
                            <div className="space-y-3">
                              <TestProgressIndicator
                                key={
                                  metricsFrozenForJobId || testStartTimestamp
                                }
                                forceDark={true}
                                useDemoStyles={true}
                                historyOverride={frozenMetrics}
                                metricsOverride={frozenMetricsSummary}
                              />
                            </div>
                          )}

                        {performanceResult && !performanceJobId && (
                          <div className="space-y-3">
                            <div className="grid grid-cols-2 gap-2">
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
                                    Total FPS
                                  </p>
                                  <p
                                    className={`text-2xl font-bold ${colors.summaryStreamsValueText}`}
                                  >
                                    {performanceSummary?.total?.toFixed(2) ??
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
                                    {performanceSummary?.perStream?.toFixed(
                                      2,
                                    ) ?? "N/A"}
                                  </p>
                                </div>
                              </div>
                            </div>

                            {hasFrozenMetrics && frozenMetricsSummary && (
                              <TestProgressIndicator
                                key={
                                  metricsFrozenForJobId || testStartTimestamp
                                }
                                className="mt-2"
                                forceDark={true}
                                useDemoStyles={true}
                                historyOverride={frozenMetrics}
                                metricsOverride={frozenMetricsSummary}
                              />
                            )}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {densityJobId && jobStatus && (
                          <div className="space-y-2">
                            {jobStatus.state === "RUNNING" && (
                              <div>
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
                                <TestProgressIndicator
                                  key={densityJobId || testStartTimestamp}
                                  forceDark={true}
                                  useDemoStyles={true}
                                />
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

                        {!testResult &&
                          !densityJobId &&
                          !errorMessage &&
                          !hasFrozenMetrics && (
                            <div className="flex items-center justify-center h-full text-slate-400">
                              <p className="text-sm">
                                Results will appear here after running the test
                              </p>
                            </div>
                          )}

                        {!testResult &&
                          hasFrozenMetrics &&
                          frozenMetricsSummary && (
                            <div className="space-y-3">
                              <TestProgressIndicator
                                key={
                                  metricsFrozenForJobId || testStartTimestamp
                                }
                                forceDark={true}
                                useDemoStyles={true}
                                historyOverride={frozenMetrics}
                                metricsOverride={frozenMetricsSummary}
                              />
                            </div>
                          )}

                        {testResult && !densityJobId && (
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
                            {hasFrozenMetrics && frozenMetricsSummary && (
                              <TestProgressIndicator
                                key={
                                  metricsFrozenForJobId || testStartTimestamp
                                }
                                className="mt-2"
                                forceDark={true}
                                useDemoStyles={true}
                                historyOverride={frozenMetrics}
                                metricsOverride={frozenMetricsSummary}
                              />
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ) : null;

              if (showPreRunLayout) {
                return (
                  <div className="h-full flex flex-col">
                    <div
                      className="grid grid-rows-[0.45fr_1.55fr] gap-4 h-full p-4"
                      style={gridColumnsStyle}
                    >
                      <div className="row-start-1 col-start-1">
                        {pipelineCardsSection}
                      </div>
                      <div className="row-start-2 col-start-1 h-full min-h-0">
                        <div className="h-full min-h-0 flex flex-col gap-4">
                          {pipelineConfigSection}
                          {actionButtonsSection}
                        </div>
                      </div>
                      <div className="row-start-1 col-start-2 row-span-2 h-full min-h-0 flex flex-col">
                        {resultsSection}
                      </div>
                    </div>
                  </div>
                );
              }

              if (showPreviewPanel) {
                return (
                  <div className="h-full flex flex-col">
                    <div
                      className="grid grid-cols-2 gap-6 h-full p-4"
                      style={gridColumnsStyle}
                    >
                      <div className="flex flex-col gap-4 h-full">
                        <div className="flex-shrink-0">
                          {pipelineCardsSection}
                        </div>
                        <div className="flex-1 min-h-0">
                          <div className="h-full min-h-0 flex flex-col gap-4">
                            {pipelineConfigSection}
                            {actionButtonsSection}
                          </div>
                        </div>
                      </div>

                      <div className="flex flex-col h-full overflow-hidden">
                        {resultsSection}
                      </div>
                    </div>
                  </div>
                );
              }

              return (
                <div className="h-full flex flex-col">
                  <div
                    className="grid grid-rows-[0.45fr_1.55fr] gap-4 h-full p-4"
                    style={gridColumnsStyle}
                  >
                    <div className="row-start-1 col-start-1">
                      {pipelineCardsSection}
                    </div>
                    <div className="row-start-2 col-start-1 h-full min-h-0">
                      <div className="h-full min-h-0 flex flex-col gap-4">
                        {pipelineConfigSection}
                        {actionButtonsSection}
                      </div>
                    </div>
                    <div className="row-start-1 col-start-2 row-span-2 h-full min-h-0 flex flex-col">
                      {resultsSection}
                    </div>
                  </div>
                </div>
              );
            })()
          ) : null}
        </div>
      </div>
      <Toaster position="top-center" richColors />
      <style>{`
        .no-spin::-webkit-outer-spin-button,
        .no-spin::-webkit-inner-spin-button {
          -webkit-appearance: none;
          margin: 0;
        }
        .no-spin {
          -moz-appearance: textfield;
        }
        @keyframes float {0%,100%{transform:translateY(0);}50%{transform:translateY(-6px);}}
        @keyframes spin {0%{transform:rotate(0deg);}100%{transform:rotate(360deg);}}
        @keyframes spin_reverse {0%{transform:rotate(360deg);}100%{transform:rotate(0deg);}}
        @keyframes fadeIn {from{opacity:0;}to{opacity:1;}}
        @keyframes slideInLeft {from{opacity:0;transform:translateX(-100px);}to{opacity:1;transform:translateX(0);}}
        @keyframes slideInRight {from{opacity:0;transform:translateX(100px);}to{opacity:1;transform:translateX(0);}}
        @keyframes softSlideInLeft {from{opacity:0;transform:translateX(-40px) scale(0.98);}to{opacity:1;transform:translateX(0) scale(1);}}
        @keyframes softSlideInRight {from{opacity:0;transform:translateX(40px) scale(0.98);}to{opacity:1;transform:translateX(0) scale(1);}}
        @keyframes gridAppear {from{opacity:0;}to{opacity:1;}}
        @keyframes slideToPosition {from{opacity:0;transform:scale(1.2);}to{opacity:1;transform:scale(1);}}
        @keyframes slideUp {from{opacity:0;transform:translateY(50px);}to{opacity:1;transform:translateY(0);}}
        @keyframes gradientShift {0%{background-position:0% 50%;}25%{background-position:100% 50%;}50%{background-position:100% 100%;}75%{background-position:0% 100%;}100%{background-position:0% 50%;}background-size:200% 200%;}
      `}</style>
    </div>
  );
};

export default DemoMode;
