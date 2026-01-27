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
import { useEffect, useRef, useState } from "react";
import PipelineEditor, {
  type PipelineEditorHandle,
} from "@/features/pipeline-editor/PipelineEditor.tsx";
import NodeDataPanel from "@/features/pipeline-editor/NodeDataPanel.tsx";
import RunPipelineButton from "@/features/pipeline-editor/RunPerformanceTestButton.tsx";
import StopPipelineButton from "@/features/pipeline-editor/StopPipelineButton.tsx";
import PerformanceTestPanel from "@/features/pipeline-editor/PerformanceTestPanel.tsx";
import { toast } from "sonner";
import ExportPipelineButton from "@/features/pipeline-editor/ExportPipelineButton.tsx";
import DeletePipelineButton from "@/features/pipeline-editor/DeletePipelineButton.tsx";
import ImportPipelineButton from "@/features/pipeline-editor/ImportPipelineButton.tsx";
import ViewModeSwitcher from "@/features/pipeline-editor/ViewModeSwitcher.tsx";
import { Zap } from "lucide-react";
import { isApiError } from "@/lib/apiUtils";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Checkbox } from "@/components/ui/checkbox";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";

type UrlParams = {
  id: string;
};

const Pipelines = () => {
  const { id } = useParams<UrlParams>();
  const [performanceTestJobId, setPerformanceTestJobId] = useState<
    string | null
  >(null);
  const [currentNodes, setCurrentNodes] = useState<ReactFlowNode[]>([]);
  const [currentEdges, setCurrentEdges] = useState<ReactFlowEdge[]>([]);
  const [currentViewport, setCurrentViewport] = useState<Viewport | undefined>(
    undefined,
  );
  const [editorKey, setEditorKey] = useState(0);
  const [shouldFitView, setShouldFitView] = useState(false);
  const [videoOutputEnabled, setVideoOutputEnabled] = useState(true);
  const [isSimpleMode, setIsSimpleMode] = useState(true);
  const [isTransitioning, setIsTransitioning] = useState(false);
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
  const [showDetailsPanel, setShowDetailsPanel] = useState(false);
  const [selectedNode, setSelectedNode] = useState<ReactFlowNode | null>(null);
  const detailsPanelSizeRef = useRef(30);
  const detailsPanelRef = useRef<HTMLDivElement>(null);
  const isResizingRef = useRef(false);
  const pipelineEditorRef = useRef<PipelineEditorHandle>(null);

  const { data, isSuccess, refetch } = useGetPipelineQuery(
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
    if (!validationJobId) return;

    const handleOptimizeAfterValidation = async () => {
      if (!id) return;

      try {
        await updatePipeline({
          pipelineId: id,
          pipelineUpdate: {
            pipeline_graph: {
              nodes: pendingOptimizationNodes.map((node) => ({
                id: node.id,
                type: node.type ?? "",
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
        handleOptimizeAfterValidation();
      } else {
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
            position: { x: 250 * index, y: 100 },
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

  const handleNodeSelect = (node: ReactFlowNode | null) => {
    if (performanceTestJobId) {
      return;
    }

    setSelectedNode(node);
    setShowDetailsPanel(!!node);

    if (node) {
      setCompletedVideoPath(null);
    }
  };

  const handleNodeDataUpdate = (
    nodeId: string,
    updatedData: Record<string, unknown>,
  ) => {
    pipelineEditorRef.current?.updateNodeData(nodeId, updatedData);

    if (selectedNode && selectedNode.id === nodeId) {
      setSelectedNode({ ...selectedNode, data: updatedData });
    }
  };

  const handleRunPipeline = async () => {
    if (!id) return;

    setCompletedVideoPath(null);
    setShowDetailsPanel(true);
    setSelectedNode(null);

    try {
      const graphData = {
        nodes: currentNodes.map((node) => ({
          id: node.id,
          type: node.type ?? "",
          data: node.data as { [key: string]: string },
        })),
        edges: currentEdges.map((edge) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
        })),
      };

      await updatePipeline({
        pipelineId: id,
        pipelineUpdate: isSimpleMode
          ? { pipeline_graph_simple: graphData }
          : { pipeline_graph: graphData },
      }).unwrap();

      const response = await runPerformanceTest({
        performanceTestSpecInput: {
          execution_config: {
            output_mode: videoOutputEnabled ? "file" : "disabled",
            max_runtime: 0,
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
      setShowDetailsPanel(false);
      setCompletedVideoPath(null);

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

  useEffect(() => {
    if (!showDetailsPanel) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (isResizingRef.current) return;

      const target = event.target as HTMLElement;

      if (
        detailsPanelRef.current &&
        !detailsPanelRef.current.contains(target)
      ) {
        const isResizeHandle =
          target.closest("[data-resize-handle]") ||
          target.closest("[data-resize-handle-active]") ||
          target.closest('[role="separator"]') ||
          target.getAttribute("data-resize-handle") !== null;

        if (!isResizeHandle) {
          if (!performanceTestJobId && !completedVideoPath) {
            setShowDetailsPanel(false);
            setSelectedNode(null);
          }
        }
      }
    };

    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showDetailsPanel, performanceTestJobId, completedVideoPath]);

  const handleOptimizePipeline = async () => {
    if (!id) return;

    setIsOptimizing(true);

    setPendingOptimizationNodes(currentNodes);
    setPendingOptimizationEdges(currentEdges);

    try {
      const pipelineGraph = {
        nodes: currentNodes.map((node) => ({
          id: node.id,
          type: node.type ?? "",
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
    const editorContent = (
      <div className="w-full h-full relative">
        <div
          className="w-full h-full transition-opacity duration-100"
          style={{ opacity: isTransitioning ? 0 : 1 }}
        >
          <PipelineEditor
            ref={pipelineEditorRef}
            key={editorKey}
            pipelineData={data}
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
            onViewportChange={handleViewportChange}
            onNodeSelect={handleNodeSelect}
            initialNodes={currentNodes.length > 0 ? currentNodes : undefined}
            initialEdges={currentEdges.length > 0 ? currentEdges : undefined}
            initialViewport={currentViewport}
            shouldFitView={shouldFitView}
            useSimpleGraph={isSimpleMode}
          />
        </div>

        <div className="absolute top-4 left-4 z-10 flex flex-col gap-2 items-start">
          <div className="flex gap-2">
            {performanceTestJobId ? (
              <StopPipelineButton
                isStopping={isStopping}
                onStop={handleStopPipeline}
              />
            ) : (
              <RunPipelineButton
                onRun={handleRunPipeline}
                isRunning={isRunning}
              />
            )}

            <button
              className="bg-background hover:bg-classic-blue dark:text-energy-blue font-medium dark:hover:text-[#242528] dark:border-energy-blue dark:hover:bg-energy-blue border-2 border-classic-blue text-primary hover:text-white px-3 py-2 transition-colors flex items-center gap-2"
              title="Optimize Pipeline"
              disabled={isOptimizing || performanceTestJobId != null}
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
            {id && (
              <ViewModeSwitcher
                pipelineId={id}
                isSimpleMode={isSimpleMode}
                currentNodes={currentNodes}
                currentEdges={currentEdges}
                onModeChange={setIsSimpleMode}
                onTransitionStart={() => setIsTransitioning(true)}
                onTransitionEnd={() => setIsTransitioning(false)}
                onClearGraph={() => {
                  setCurrentNodes([]);
                  setCurrentEdges([]);
                }}
                onRefetch={refetch}
                onEditorKeyChange={() => setEditorKey((prev) => prev + 1)}
              />
            )}
          </div>

          <div className="flex gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <label className="bg-background p-2 flex items-center gap-2 cursor-pointer">
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
        </div>
      </div>
    );

    return (
      <ResizablePanelGroup
        orientation="horizontal"
        className="w-full h-full"
        onLayoutChange={(sizes) => {
          const sizeValues = Object.values(sizes);
          if (sizeValues.length === 2) {
            detailsPanelSizeRef.current = sizeValues[1];
          }
        }}
      >
        <ResizablePanel
          defaultSize={
            showDetailsPanel ? 100 - detailsPanelSizeRef.current : 100
          }
          minSize={30}
        >
          {editorContent}
        </ResizablePanel>

        {showDetailsPanel && (
          <>
            <ResizableHandle withHandle />

            <ResizablePanel
              defaultSize={detailsPanelSizeRef.current}
              minSize={20}
            >
              <div
                ref={detailsPanelRef}
                className="w-full h-full bg-background overflow-auto relative"
              >
                {showDetailsPanel && !selectedNode ? (
                  <PerformanceTestPanel
                    isRunning={performanceTestJobId != null}
                    completedVideoPath={completedVideoPath}
                  />
                ) : (
                  <NodeDataPanel
                    selectedNode={selectedNode}
                    onNodeDataUpdate={handleNodeDataUpdate}
                  />
                )}
              </div>
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>
    );
  }

  return <div>Loading pipeline: {id}</div>;
};

export default Pipelines;
