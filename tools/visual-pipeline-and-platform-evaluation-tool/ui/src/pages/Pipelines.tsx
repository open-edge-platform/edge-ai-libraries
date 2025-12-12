import { useParams } from "react-router";
import {
  useGetOptimizationJobStatusQuery,
  useGetPerformanceJobStatusQuery,
  useGetPipelineQuery,
  useGetValidationJobStatusQuery,
  useOptimizePipelineMutation,
  useRunPerformanceTestMutation,
  useStopPerformanceTestJobMutation,
  useUpdatePipelineMutation,
  useValidatePipelineMutation,
} from "@/api/api.generated";
import {
  type Edge as ReactFlowEdge,
  type Node as ReactFlowNode,
  type Viewport,
} from "@xyflow/react";
import { useEffect, useState } from "react";
import PipelineEditor from "@/features/pipeline-editor/PipelineEditor.tsx";
import FpsDisplay from "@/features/pipeline-editor/FpsDisplay.tsx";
import { toast } from "sonner";
import RunPerformanceTestButton from "@/features/pipeline-editor/RunPerformanceTestButton.tsx";
import StopPerformanceTestButton from "@/features/pipeline-editor/StopPerformanceTestButton.tsx";
import ExportPipelineButton from "@/features/pipeline-editor/ExportPipelineButton.tsx";
import DeletePipelineButton from "@/features/pipeline-editor/DeletePipelineButton.tsx";
import ImportPipelineButton from "@/features/pipeline-editor/ImportPipelineButton.tsx";
import DeviceSelect from "@/components/shared/DeviceSelect";
import { Zap } from "lucide-react";
import { isApiError } from "@/lib/apiUtils";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Checkbox } from "@/components/ui/checkbox";
import { useAppSelector } from "@/store/hooks";
import { selectDevices } from "@/store/reducers/devices";

type UrlParams = {
  id: string;
};

const Pipelines = () => {
  const { id } = useParams<UrlParams>();
  const devices = useAppSelector(selectDevices);
  const [performanceTestJobId, setPerformanceTestJobId] = useState<
    string | null
  >(null);
  const [currentNodes, setCurrentNodes] = useState<ReactFlowNode[]>([]);
  const [currentEdges, setCurrentEdges] = useState<ReactFlowEdge[]>([]);
  const [currentViewport, setCurrentViewport] = useState<Viewport>({
    x: 0,
    y: 0,
    zoom: 1,
  });
  const [editorKey, setEditorKey] = useState(0);
  const [shouldFitView, setShouldFitView] = useState(false);
  const [videoOutputEnabled, setVideoOutputEnabled] = useState(true);
  const [encoderDevice, setEncoderDevice] = useState<string>("CPU");
  const [completedVideoPath, setCompletedVideoPath] = useState<string | null>(
    null,
  );
  const [validationJobId, setValidationJobId] = useState<string | null>(null);
  const [optimizationJobId, setOptimizationJobId] = useState<string | null>(
    null,
  );
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [pendingOptimizationNodes, setPendingOptimizationNodes] = useState<
    ReactFlowNode[]
  >([]);
  const [pendingOptimizationEdges, setPendingOptimizationEdges] = useState<
    ReactFlowEdge[]
  >([]);

  const { data, isSuccess } = useGetPipelineQuery(
    {
      pipelineId: id ?? "",
    },
    {
      skip: !id,
    },
  );

  const [runPerformanceTest, { isLoading: isRunning }] =
    useRunPerformanceTestMutation();
  const [stopPerformanceTest, { isLoading: isStopping }] =
    useStopPerformanceTestJobMutation();
  const [updatePipeline] = useUpdatePipelineMutation();
  const [validatePipeline] = useValidatePipelineMutation();
  const [optimizePipeline] = useOptimizePipelineMutation();

  const { data: jobStatus } = useGetPerformanceJobStatusQuery(
    { jobId: performanceTestJobId! },
    {
      skip: !performanceTestJobId,
      pollingInterval: 1000,
    },
  );

  const { data: validationStatus, error: validationError } =
    useGetValidationJobStatusQuery(
      { jobId: validationJobId! },
      {
        skip: !validationJobId,
        pollingInterval: 1000,
      },
    );

  const { data: optimizationStatus, error: optimizationError } =
    useGetOptimizationJobStatusQuery(
      { jobId: optimizationJobId! },
      {
        skip: !optimizationJobId,
        pollingInterval: 1000,
      },
    );

  useEffect(() => {
    if (jobStatus?.state === "COMPLETED") {
      toast.success("Pipeline run completed", {
        description: new Date().toISOString(),
      });

      // Extract video path if available
      if (videoOutputEnabled && jobStatus.video_output_paths && id) {
        const paths = jobStatus.video_output_paths[id];
        if (paths && paths.length > 0) {
          const videoPath = [...paths].pop();
          if (videoPath) {
            setCompletedVideoPath(videoPath);
          }
        }
      }

      setPerformanceTestJobId(null);
    } else if (jobStatus?.state === "ERROR" || jobStatus?.state === "ABORTED") {
      toast.error("Pipeline run failed", {
        description: jobStatus.error_message || "Unknown error",
      });
      setPerformanceTestJobId(null);
    }
  }, [jobStatus, videoOutputEnabled, id]);

  // Handle validation job status query errors
  useEffect(() => {
    if (validationError && validationJobId) {
      toast.error("Failed to get validation status", {
        description: "An error occurred while checking validation status",
      });
      setIsOptimizing(false);
      setValidationJobId(null);
      setPendingOptimizationNodes([]);
      setPendingOptimizationEdges([]);
    }
  }, [validationError, validationJobId]);

  // Handle optimization job status query errors
  useEffect(() => {
    if (optimizationError && optimizationJobId) {
      toast.error("Failed to get optimization status", {
        description: "An error occurred while checking optimization status",
      });
      setIsOptimizing(false);
      setOptimizationJobId(null);
      setPendingOptimizationNodes([]);
      setPendingOptimizationEdges([]);
    }
  }, [optimizationError, optimizationJobId]);

  useEffect(() => {
    // Guard: only process if we have an active validation job
    if (!validationJobId) return;

    const handleOptimizeAfterValidation = async () => {
      if (!id) return;

      try {
        // Step 2: Update pipeline with snapshot graph
        await updatePipeline({
          pipelineId: id,
          pipelineUpdate: {
            pipeline_graph: {
              nodes: pendingOptimizationNodes.map((node) => ({
                id: node.id,
                type: node.type || "",
                data: node.data as { [key: string]: string },
              })),
              edges: pendingOptimizationEdges.map((edge) => ({
                id: edge.id,
                source: edge.source,
                target: edge.target,
              })),
            },
          },
        }).unwrap();

        // Step 3: Start optimization
        const optimizationResponse = await optimizePipeline({
          pipelineId: id,
          pipelineRequestOptimize: {
            type: "optimize",
            parameters: {
              search_duration: 300,
              sample_duration: 10,
            },
          },
        }).unwrap();

        if (optimizationResponse && "job_id" in optimizationResponse) {
          setOptimizationJobId(optimizationResponse.job_id);
          toast.info("Optimizing pipeline...");
        }
      } catch (error) {
        const errorMessage = isApiError(error)
          ? error.data.message
          : "Unknown error";
        toast.error("Failed to start optimization", {
          description: errorMessage,
        });
        setIsOptimizing(false);
        setPendingOptimizationNodes([]);
        setPendingOptimizationEdges([]);
        console.error("Failed to start optimization:", error);
      }
    };

    if (validationStatus?.state === "COMPLETED") {
      if (validationStatus.is_valid) {
        // Validation passed, proceed to optimization
        handleOptimizeAfterValidation();
      } else {
        // Validation failed
        toast.error("Pipeline validation failed", {
          description:
            validationStatus.error_message?.join(", ") || "Unknown error",
        });
        setIsOptimizing(false);
        setPendingOptimizationNodes([]);
        setPendingOptimizationEdges([]);
      }
      setValidationJobId(null);
    } else if (
      validationStatus?.state === "ERROR" ||
      validationStatus?.state === "ABORTED"
    ) {
      toast.error("Validation job failed", {
        description:
          validationStatus.error_message?.join(", ") || "Unknown error",
      });
      setIsOptimizing(false);
      setPendingOptimizationNodes([]);
      setPendingOptimizationEdges([]);
      setValidationJobId(null);
    }
  }, [
    validationStatus,
    validationJobId,
    id,
    pendingOptimizationNodes,
    pendingOptimizationEdges,
    updatePipeline,
    optimizePipeline,
  ]);

  useEffect(() => {
    const applyOptimizedPipeline = async (optimizedGraph: {
      nodes: { id: string; type: string; data: { [key: string]: string } }[];
      edges: { id: string; source: string; target: string }[];
    }) => {
      if (!id) return;

      try {
        // Dismiss the toast first
        toast.dismiss();

        // Step 1: Save optimized pipeline to backend
        await updatePipeline({
          pipelineId: id,
          pipelineUpdate: {
            pipeline_graph: optimizedGraph,
          },
        }).unwrap();

        // Step 2: Convert optimized graph to ReactFlow format with layout
        const newNodes: ReactFlowNode[] = optimizedGraph.nodes.map(
          (node, index) => ({
            id: node.id,
            type: node.type,
            data: node.data,
            position: { x: 250 * index, y: 100 }, // Basic horizontal layout
          }),
        );

        const newEdges: ReactFlowEdge[] = optimizedGraph.edges.map((edge) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
        }));

        // Step 3: Update local state
        setCurrentNodes(newNodes);
        setCurrentEdges(newEdges);
        setShouldFitView(true);
        setEditorKey((prev) => prev + 1); // Force re-render with layout

        // Clear optimization state
        setPendingOptimizationNodes([]);
        setPendingOptimizationEdges([]);

        toast.success("Optimized pipeline applied");
      } catch (error) {
        const errorMessage = isApiError(error)
          ? error.data.message
          : "Unknown error";
        toast.error("Failed to apply optimized pipeline", {
          description: errorMessage,
        });
        console.error("Failed to apply optimized pipeline:", error);
      }
    };

    if (optimizationStatus?.state === "COMPLETED") {
      const optimizedGraph = optimizationStatus.optimized_pipeline_graph;

      if (optimizedGraph) {
        // Show toast with Apply/Cancel buttons
        toast.success("Pipeline optimization completed", {
          duration: Infinity,
          description: "Would you like to apply the optimized pipeline?",
          action: {
            label: "Apply",
            onClick: () => {
              applyOptimizedPipeline(optimizedGraph);
            },
          },
          cancel: {
            label: "Cancel",
            onClick: () => {
              toast.dismiss();
              setPendingOptimizationNodes([]);
              setPendingOptimizationEdges([]);
            },
          },
        });
      } else {
        toast.error("Optimization completed but no optimized graph available");
      }

      setIsOptimizing(false);
      setOptimizationJobId(null);
    } else if (
      optimizationStatus?.state === "ERROR" ||
      optimizationStatus?.state === "ABORTED"
    ) {
      toast.error("Optimization job failed", {
        description: optimizationStatus.error_message || "Unknown error",
      });
      setIsOptimizing(false);
      setOptimizationJobId(null);
    }
  }, [optimizationStatus, id, updatePipeline]);

  const handleNodesChange = (nodes: ReactFlowNode[]) => {
    setCurrentNodes(nodes);
  };

  const handleEdgesChange = (edges: ReactFlowEdge[]) => {
    setCurrentEdges(edges);
  };

  const handleViewportChange = (viewport: Viewport) => {
    setCurrentViewport(viewport);
  };

  const handleRunPipeline = async () => {
    if (!id) return;

    setCompletedVideoPath(null); // Clear previous video

    try {
      await updatePipeline({
        pipelineId: id,
        pipelineUpdate: {
          pipeline_graph: {
            nodes: currentNodes.map((node) => ({
              id: node.id,
              type: node.type || "",
              data: node.data as { [key: string]: string },
            })),
            edges: currentEdges.map((edge) => ({
              id: edge.id,
              source: edge.source,
              target: edge.target,
            })),
          },
        },
      }).unwrap();

      const selectedDevice = devices.find(
        (d) => d.device_name === encoderDevice,
      );

      const response = await runPerformanceTest({
        performanceTestSpecInput: {
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
          pipeline_performance_specs: [
            {
              id,
              streams: 1,
            },
          ],
        },
      }).unwrap();

      if (response && typeof response === "object" && "job_id" in response) {
        setPerformanceTestJobId(response.job_id as string);
      }

      toast.success("Pipeline run started", {
        description: new Date().toISOString(),
      });
    } catch (error) {
      const errorMessage = isApiError(error)
        ? error.data.message
        : "Unknown error";
      toast.error("Failed to start pipeline", {
        description: errorMessage,
      });
      console.error("Failed to start pipeline:", error);
    }
  };

  const handleStopPipeline = async () => {
    if (!performanceTestJobId) return;

    try {
      await stopPerformanceTest({
        jobId: performanceTestJobId,
      }).unwrap();

      setPerformanceTestJobId(null);

      toast.success("Pipeline stopped", {
        description: new Date().toISOString(),
      });
    } catch (error) {
      const errorMessage = isApiError(error)
        ? error.data.message
        : "Unknown error";
      toast.error("Failed to stop pipeline", {
        description: errorMessage,
      });
      console.error("Failed to stop pipeline:", error);
    }
  };

  const handleImport = (
    nodes: ReactFlowNode[],
    edges: ReactFlowEdge[],
    viewport: Viewport,
    shouldFitView: boolean,
  ) => {
    setCurrentNodes(nodes);
    setCurrentEdges(edges);
    setCurrentViewport(viewport);
    setShouldFitView(shouldFitView);
    setEditorKey((prev) => prev + 1); // Force PipelineEditor to re-initialize
  };

  const handleOptimizePipeline = async () => {
    if (!id) return;

    setIsOptimizing(true);

    // Capture snapshot of current graph for optimization
    setPendingOptimizationNodes(currentNodes);
    setPendingOptimizationEdges(currentEdges);

    try {
      // Step 1: Validate pipeline
      const pipelineGraph = {
        nodes: currentNodes.map((node) => ({
          id: node.id,
          type: node.type || "",
          data: node.data as { [key: string]: string },
        })),
        edges: currentEdges.map((edge) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
        })),
      };

      const validationResponse = await validatePipeline({
        pipelineValidationInput: {
          pipeline_graph: pipelineGraph,
        },
      }).unwrap();

      if (validationResponse && "job_id" in validationResponse) {
        setValidationJobId(validationResponse.job_id);
        toast.info("Validating pipeline...");
      }
    } catch (error) {
      const errorMessage = isApiError(error)
        ? error.data.message
        : "Unknown error";
      toast.error("Failed to start validation", {
        description: errorMessage,
      });
      setIsOptimizing(false);
      setPendingOptimizationNodes([]);
      setPendingOptimizationEdges([]);
      console.error("Failed to start validation:", error);
    }
  };

  if (isSuccess && data) {
    return (
      <div className="w-full h-full relative">
        <PipelineEditor
          key={editorKey}
          pipelineData={data}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onViewportChange={handleViewportChange}
          initialNodes={currentNodes.length > 0 ? currentNodes : undefined}
          initialEdges={currentEdges.length > 0 ? currentEdges : undefined}
          initialViewport={
            currentNodes.length > 0 ? currentViewport : undefined
          }
          shouldFitView={shouldFitView}
        />

        <div className="absolute top-4 right-4 flex flex-col gap-2 items-center">
          <FpsDisplay />
          {completedVideoPath && (
            <div className="bg-white p-2 shadow-lg">
              <video
                controls
                className="w-64 h-auto"
                src={`/assets${completedVideoPath}`}
              >
                Your browser does not support the video tag.
              </video>
            </div>
          )}
        </div>

        <div className="absolute top-4 left-4 z-10 flex flex-col gap-2 items-start">
          <div className="flex gap-2">
            {performanceTestJobId ? (
              <StopPerformanceTestButton
                isStopping={isStopping}
                onStop={handleStopPipeline}
              />
            ) : (
              <RunPerformanceTestButton
                isRunning={isRunning}
                onRun={handleRunPipeline}
              />
            )}

            <button
              className="bg-white hover:bg-carbon border border-classic-blue text-primary hover:text-white px-3 py-2 transition-colors disabled:opacity-50 disabled:hover:bg-orange-600 flex items-center gap-2"
              title="Optimize Pipeline"
              disabled={isOptimizing || !!performanceTestJobId}
              onClick={handleOptimizePipeline}
            >
              <Zap className="w-5 h-5" />
              <span>{isOptimizing ? "Optimizing..." : "Optimize"}</span>
            </button>

            <ImportPipelineButton onImport={handleImport} />

            <ExportPipelineButton
              edges={currentEdges}
              nodes={currentNodes}
              viewport={currentViewport}
              pipelineName={data.name}
            />

            {id && (
              <DeletePipelineButton pipelineId={id} pipelineName={data.name} />
            )}
          </div>

          <div className="flex gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <label className="bg-white p-2 flex items-center gap-2 cursor-pointer">
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
            {videoOutputEnabled && (
              <DeviceSelect
                value={encoderDevice}
                onChange={setEncoderDevice}
                className="bg-white p-2 text-sm font-medium cursor-pointer border-none outline-none"
              />
            )}
          </div>
          {videoOutputEnabled && (
            <div className="text-muted-foreground border border-amber-400 my-2 p-2 bg-amber-200/50 w-[634px]">
              <b>Note</b>: The current implementation does not automatically
              infer the best encoding device from the existing pipeline. Select
              the same device that is already used by other blocks in your
              pipeline. To learn more, refer to our documentation:{" "}
              <a
                href="https://docs.openedgeplatform.intel.com/2025.2/edge-ai-libraries/visual-pipeline-and-platform-evaluation-tool/index.html"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-classic-blue transition-colors underline"
              >
                link
              </a>
              .
            </div>
          )}
        </div>
      </div>
    );
  }

  return <div>Loading pipeline: {id}</div>;
};

export default Pipelines;
