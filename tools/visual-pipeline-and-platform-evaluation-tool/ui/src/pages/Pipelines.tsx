import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import {
  useConvertSimpleToAdvancedMutation,
  useGetPerformanceJobStatusQuery,
  useGetPipelineQuery,
  useRunPerformanceTestMutation,
  useStopPerformanceTestJobMutation,
  useUpdateVariantMutation,
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
import { useAsyncJob } from "@/hooks/useAsyncJob";
import NodeDataPanel from "@/features/pipeline-editor/NodeDataPanel.tsx";
import RunPipelineButton from "@/features/pipeline-editor/RunPerformanceTestButton.tsx";
import StopPipelineButton from "@/features/pipeline-editor/StopPipelineButton.tsx";
import PerformanceTestPanel from "@/features/pipeline-editor/PerformanceTestPanel.tsx";
import { toast } from "sonner";
import ViewModeSwitcher from "@/features/pipeline-editor/ViewModeSwitcher.tsx";
import { PipelineActionsMenu } from "@/features/pipeline-editor/PipelineActionsMenu";
import {
  handleApiError,
  handleAsyncJobError,
  isAsyncJobError,
} from "@/lib/apiUtils";
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
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

type UrlParams = {
  id: string;
  variant: string;
};

export const Pipelines = () => {
  const { id, variant } = useParams<UrlParams>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const source = searchParams.get("source");
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

  const [stopPerformanceTest, { isLoading: isStopping }] =
    useStopPerformanceTestJobMutation();
  const [convertSimpleToAdvanced] = useConvertSimpleToAdvancedMutation();
  const [updateVariant] = useUpdateVariantMutation();

  const {
    execute: runPipeline,
    isLoading: isPipelineRunning,
    jobStatus,
  } = useAsyncJob({
    asyncJobHook: useRunPerformanceTestMutation,
    statusCheckHook: useGetPerformanceJobStatusQuery,
  });

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

  const handleSave = async () => {
    if (!id || !variant) return;

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

      await updateVariant({
        pipelineId: id,
        variantId: variant,
        variantUpdate: isSimpleMode
          ? { pipeline_graph_simple: graphData }
          : { pipeline_graph: graphData },
      }).unwrap();

      resetHistory();
    } catch (error) {
      handleApiError(error, "Failed to save variant");
      console.error("Failed to save variant:", error);
    }
  };

  const handleNodeSelect = (node: ReactFlowNode | null) => {
    if (jobStatus?.state === "RUNNING") {
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

      toast.success("Pipeline run started", {
        description: new Date().toISOString(),
      });

      const status = await runPipeline({
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
      });

      toast.success("Pipeline run completed", {
        description: new Date().toISOString(),
      });

      if (videoOutputEnabled && status.video_output_paths) {
        const paths = Object.values(status.video_output_paths)[0];
        if (paths && paths.length > 0) {
          const videoPath = [...paths].pop();
          if (videoPath) {
            setCompletedVideoPath(videoPath);
          }
        }
      }
    } catch (error) {
      if (isAsyncJobError(error)) {
        handleAsyncJobError(error, "Pipeline run");
      } else {
        handleApiError(error, "Failed to start pipeline");
      }
      console.error("Failed to start pipeline:", error);
    }
  };

  const handleStopPipeline = async () => {
    if (!jobStatus?.id) return;

    try {
      await stopPerformanceTest({
        jobId: jobStatus.id,
      }).unwrap();

      setShowDetailsPanel(false);
      setCompletedVideoPath(null);

      toast.success("Pipeline stopped", {
        description: new Date().toISOString(),
      });
    } catch (error) {
      handleApiError(error, "Failed to stop pipeline");
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
          if (jobStatus?.state !== "RUNNING" && !completedVideoPath) {
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
  }, [showDetailsPanel, jobStatus?.state, completedVideoPath]);

  if (isSuccess && data) {
    const currentVariantData = data.variants.find((v) => v.id === variant);
    const isReadOnly = currentVariantData?.read_only ?? false;

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
                <Button
                  onClick={undo}
                  disabled={!canUndo}
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Undo"
                >
                  <Undo2 className="h-5 w-5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p>Undo (Ctrl+Z)</p>
              </TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  onClick={redo}
                  disabled={!canRedo}
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Redo"
                >
                  <Redo2 className="h-5 w-5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p>Redo (Ctrl+Y)</p>
              </TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  onClick={handleSave}
                  disabled={isReadOnly || !canUndo}
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Save"
                >
                  <Save className="h-5 w-5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p>
                  {isReadOnly
                    ? "Read-only variant cannot be saved."
                    : !canUndo
                      ? "No changes to save"
                      : "Save (Ctrl+S)"}
                </p>
              </TooltipContent>
            </Tooltip>

            <Separator orientation="vertical" className="h-6" />

            {jobStatus?.state === "RUNNING" ? (
              <StopPipelineButton
                isStopping={isStopping}
                onStop={handleStopPipeline}
              />
            ) : (
              <RunPipelineButton
                onRun={handleRunPipeline}
                isRunning={isPipelineRunning}
              />
            )}
            <PipelineActionsMenu
              pipeline={data}
              variantId={variant!}
              currentNodes={currentNodes}
              currentEdges={currentEdges}
              currentViewport={currentViewport}
              isSimpleMode={isSimpleMode}
              isReadOnly={isReadOnly}
              performanceTestJobId={jobStatus?.id ?? null}
              onGraphUpdate={updateGraph}
              onVariantRenamed={() => {
                refetch();
              }}
              onVariantDeleted={() => {
                const remainingVariants = data.variants.filter(
                  (v) => v.id !== variant,
                );
                const firstVariant = remainingVariants[0];
                if (firstVariant) {
                  navigate(`/pipelines/${id}/${firstVariant.id}`);
                } else {
                  navigate("/pipelines");
                }
              }}
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
                        isRunning={jobStatus?.state === "RUNNING"}
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
