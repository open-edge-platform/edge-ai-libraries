import { Link, useParams, useSearchParams } from "react-router";
import {
  useConvertSimpleToAdvancedMutation,
  useGetPerformanceJobStatusQuery,
  useGetPipelineQuery,
  useRunPerformanceTestMutation,
  useStopPerformanceTestJobMutation,
} from "@/api/api.generated";
import { PipelineVariantSelect } from "@/features/pipelines/PipelineVariantSelect";
import {
  type Edge as ReactFlowEdge,
  type Node as ReactFlowNode,
  type Viewport,
} from "@xyflow/react";
import { useEffect, useRef, useState } from "react";
import PipelineEditor, {
  type PipelineEditorHandle,
} from "@/features/pipeline-editor/PipelineEditor.tsx";
import { useUndoRedo } from "@/hooks/useUndoRedo";
import NodeDataPanel from "@/features/pipeline-editor/NodeDataPanel.tsx";
import RunPipelineButton from "@/features/pipeline-editor/RunPerformanceTestButton.tsx";
import StopPipelineButton from "@/features/pipeline-editor/StopPipelineButton.tsx";
import PerformanceTestPanel from "@/features/pipeline-editor/PerformanceTestPanel.tsx";
import { toast } from "sonner";
import ViewModeSwitcher from "@/features/pipeline-editor/ViewModeSwitcher.tsx";
import { PipelineActionsMenu } from "@/features/pipeline-editor/PipelineActionsMenu";
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
import { ArrowLeft, Redo2, Save, Undo2 } from "lucide-react";
import { PipelineName } from "@/features/pipelines/PipelineName.tsx";

type UrlParams = {
  id: string;
  variant: string;
};

export const Pipelines = () => {
  const { id, variant } = useParams<UrlParams>();
  const [searchParams] = useSearchParams();
  const source = searchParams.get("source");
  const [performanceTestJobId, setPerformanceTestJobId] = useState<
    string | null
  >(null);
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
  const [showDetailsPanel, setShowDetailsPanel] = useState(false);
  const [selectedNode, setSelectedNode] = useState<ReactFlowNode | null>(null);
  const detailsPanelSizeRef = useRef(30);
  const detailsPanelRef = useRef<HTMLDivElement>(null);
  const isResizingRef = useRef(false);
  const pipelineEditorRef = useRef<PipelineEditorHandle>(null);

  const {
    currentNodes,
    currentEdges,
    canUndo,
    canRedo,
    handleNodesChange,
    handleEdgesChange,
    setCurrentNodes,
    setCurrentEdges,
    undo: undoHistory,
    redo: redoHistory,
    resetHistory,
  } = useUndoRedo();

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
  const [convertSimpleToAdvanced] = useConvertSimpleToAdvancedMutation();

  const { data: jobStatus } = useGetPerformanceJobStatusQuery(
    { jobId: performanceTestJobId! },
    {
      skip: !performanceTestJobId,
      pollingInterval: 1000,
    },
  );

  useEffect(() => {
    if (jobStatus?.state === "COMPLETED") {
      toast.success("Pipeline run completed", {
        description: new Date().toISOString(),
      });

      if (videoOutputEnabled && jobStatus.video_output_paths) {
        // const paths = jobStatus.video_output_paths[id]; // TODO: Fix key mismatch - not using pipelineId as key
        const paths = Object.values(jobStatus.video_output_paths)[0];
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

  // Reset editor state when variant changes
  useEffect(() => {
    setCurrentNodes([]);
    setCurrentEdges([]);
    setCurrentViewport(undefined);
    setShouldFitView(true);
    setEditorKey((prev) => prev + 1);
    setSelectedNode(null);
    setShowDetailsPanel(false);
    setCompletedVideoPath(null);
    resetHistory();
  }, [variant, resetHistory, setCurrentNodes, setCurrentEdges]);

  const handleViewportChange = (viewport: Viewport) => {
    setCurrentViewport(viewport);
  };

  const isUndoRedoRef = useRef(false);

  const undo = () => {
    isUndoRedoRef.current = true;
    undoHistory();
  };

  const redo = () => {
    isUndoRedoRef.current = true;
    redoHistory();
  };

  useEffect(() => {
    if (isUndoRedoRef.current && pipelineEditorRef.current) {
      pipelineEditorRef.current.setNodes(currentNodes);
      pipelineEditorRef.current.setEdges(currentEdges);
      isUndoRedoRef.current = false;
    }
  }, [currentNodes, currentEdges]);

  const handleSave = () => {
    // TODO: Implement save functionality
    console.log("Save clicked");
    // After successful save, call: resetHistory();
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

    setCurrentNodes((prevNodes) =>
      prevNodes.map((node) =>
        node.id === nodeId ? { ...node, data: updatedData } : node,
      ),
    );

    if (selectedNode && selectedNode.id === nodeId) {
      setSelectedNode({ ...selectedNode, data: updatedData });
    }
  };

  const handleRunPipeline = async () => {
    if (!id || !variant) return;

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

      let payloadGraphData = graphData;
      if (isSimpleMode) {
        payloadGraphData = await convertSimpleToAdvanced({
          pipelineId: id,
          variantId: variant,
          pipelineGraph: graphData,
        }).unwrap();
      }

      const response = await runPerformanceTest({
        performanceTestSpec: {
          pipeline_performance_specs: [
            {
              pipeline: {
                source: "graph",
                pipeline_graph: payloadGraphData,
              },
              streams: 1,
            },
          ],
          execution_config: {
            output_mode: videoOutputEnabled ? "file" : "disabled",
            max_runtime: 0,
          },
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

  const updateGraph = (
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
            variant={variant}
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
            onViewportChange={handleViewportChange}
            onNodeSelect={handleNodeSelect}
            initialNodes={currentNodes.length > 0 ? currentNodes : undefined}
            initialEdges={currentEdges.length > 0 ? currentEdges : undefined}
            initialViewport={currentViewport}
            shouldFitView={shouldFitView}
            isSimpleGraph={isSimpleMode}
          />
        </div>

        <div className="absolute top-4 left-4 z-10 flex flex-col gap-2 items-start">
          <div className="flex gap-2">
            {id && variant && (
              <ViewModeSwitcher
                pipelineId={id}
                variant={variant}
                isPredefined={data.source === "PREDEFINED"}
                isSimpleMode={isSimpleMode}
                currentNodes={currentNodes}
                currentEdges={currentEdges}
                hasUnsavedChanges={canUndo}
                onModeChange={setIsSimpleMode}
                onTransitionStart={() => setIsTransitioning(true)}
                onTransitionEnd={() => setIsTransitioning(false)}
                onClearGraph={() => {
                  setCurrentNodes([]);
                  setCurrentEdges([]);
                }}
                onRefetch={refetch}
                onEditorKeyChange={() => setEditorKey((prev) => prev + 1)}
                onResetHistory={resetHistory}
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
      <div className="flex flex-col h-full w-full">
        <header className="flex h-[60px] shrink-0 items-center gap-2 justify-between transition-[width,height] ease-linear border-b">
          <div className="flex items-center gap-2 px-2">
            <Link
              to={source === "dashboard" ? "/" : "/pipelines"}
              className="p-2 hover:bg-accent rounded transition-colors"
            >
              <ArrowLeft className="h-5 w-5" />
            </Link>
            {id && <PipelineName pipelineId={id} />}
            {id && variant && (
              <PipelineVariantSelect
                pipelineId={id}
                currentVariant={variant}
                variants={data.variants}
                source={source}
                hasUnsavedChanges={canUndo}
              />
            )}
          </div>
          <div className="flex items-center gap-2 px-4">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={undo}
                  disabled={!canUndo}
                  className="p-2 hover:bg-accent rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  aria-label="Undo"
                >
                  <Undo2 className="h-5 w-5" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p>Undo (Ctrl+Z)</p>
              </TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={redo}
                  disabled={!canRedo}
                  className="p-2 hover:bg-accent rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  aria-label="Redo"
                >
                  <Redo2 className="h-5 w-5" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p>Redo (Ctrl+Y)</p>
              </TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={handleSave}
                  className="p-2 hover:bg-accent rounded transition-colors"
                  aria-label="Save"
                >
                  <Save className="h-5 w-5" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p>Save (Ctrl+S)</p>
              </TooltipContent>
            </Tooltip>

            <div className="w-px h-6 bg-border" />

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
            <PipelineActionsMenu
              pipelineId={id!}
              variant={variant!}
              currentNodes={currentNodes}
              currentEdges={currentEdges}
              currentViewport={currentViewport}
              pipelineName={data.name}
              isSimpleMode={isSimpleMode}
              performanceTestJobId={performanceTestJobId}
              onGraphUpdate={updateGraph}
            />
          </div>
        </header>
        <div className="flex-1 overflow-hidden">
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
        </div>
      </div>
    );
  }

  return <div>Loading pipeline: {id}</div>;
};
