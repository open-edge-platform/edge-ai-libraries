import { useState } from "react";
import type { Pipeline } from "@/api/api.generated";
import {
  useGetOptimizationJobStatusQuery,
  useGetValidationJobStatusQuery,
  useOptimizeVariantMutation,
  useToDescriptionMutation,
  useToGraphMutation,
  useUpdateVariantMutation,
  useValidatePipelineMutation,
} from "@/api/api.generated";
import { useAsyncJob } from "@/hooks/useAsyncJob";
import {
  type Edge as ReactFlowEdge,
  type Node as ReactFlowNode,
  type Viewport,
} from "@xyflow/react";
import {
  Download,
  FileJson,
  Lock,
  MoreVertical,
  PencilLine,
  Save,
  Terminal,
  Trash2,
  Upload,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { handleApiError } from "@/lib/apiUtils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { EditVariantDialog } from "@/features/pipelines/EditVariantDialog";
import { DeletePipelineVariantDialog } from "@/features/pipelines/DeletePipelineVariantDialog";
import { DeletePipelineDialog } from "@/features/pipelines/DeletePipelineDialog";
import { formatErrorMessage } from "@/lib/utils.ts";

interface PipelineActionsMenuProps {
  pipeline: Pipeline;
  variantId: string;
  currentNodes: ReactFlowNode[];
  currentEdges: ReactFlowEdge[];
  currentViewport?: Viewport;
  isSimpleMode: boolean;
  isReadOnly: boolean;
  performanceTestJobId: string | null;
  onGraphUpdate: (
    nodes: ReactFlowNode[],
    edges: ReactFlowEdge[],
    viewport: Viewport,
    shouldFitView: boolean,
  ) => void;
  onVariantDeleted?: () => void;
  onVariantRenamed?: () => void;
}

export const PipelineActionsMenu = ({
  pipeline,
  variantId,
  currentNodes,
  currentEdges,
  currentViewport,
  isSimpleMode,
  isReadOnly,
  performanceTestJobId,
  onGraphUpdate,
  onVariantDeleted,
  onVariantRenamed,
}: PipelineActionsMenuProps) => {
  const pipelineId = pipeline.id;
  const pipelineName = pipeline.name;
  const variantName =
    pipeline.variants.find((v) => v.id === variantId)?.name ?? "";
  const variantsCount = pipeline.variants.length;

  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [editVariantDialogOpen, setEditVariantDialogOpen] = useState(false);
  const [editVariantMode, setEditVariantMode] = useState<"create" | "edit">(
    "create",
  );
  const [deleteVariantDialogOpen, setDeleteVariantDialogOpen] = useState(false);
  const [deletePipelineDialogOpen, setDeletePipelineDialogOpen] =
    useState(false);
  const [pipelineDescription, setPipelineDescription] = useState("");
  const [isImporting, setIsImporting] = useState(false);

  const [toDescription, { isLoading: isExportingDescription }] =
    useToDescriptionMutation();
  const [toGraph] = useToGraphMutation();
  const [updateVariant] = useUpdateVariantMutation();

  const { execute: executeValidation, isLoading: isValidating } = useAsyncJob({
    asyncJobHook: useValidatePipelineMutation,
    statusCheckHook: useGetValidationJobStatusQuery,
  });

  const { execute: executeOptimization, isLoading: isOptimizing } = useAsyncJob(
    {
      asyncJobHook: useOptimizeVariantMutation,
      statusCheckHook: useGetOptimizationJobStatusQuery,
    },
  );

  const handleImportJson = () => {
    document.getElementById("import-pipeline-input")?.click();
  };

  const handleExportJson = () => {
    const exportData = {
      nodes: currentNodes,
      edges: currentEdges,
      viewport: currentViewport,
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${pipelineName || "pipeline"}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success("Pipeline state downloaded");
  };

  const handleExportDescription = async () => {
    try {
      const apiNodes = currentNodes.map((node) => ({
        id: node.id,
        type: node.type ?? "default",
        data: Object.fromEntries(
          Object.entries(node.data ?? {}).map(([key, value]) => [
            key,
            typeof value === "object" && value !== null
              ? JSON.stringify(value)
              : String(value),
          ]),
        ),
      }));

      const response = await toDescription({
        pipelineGraph: {
          nodes: apiNodes,
          edges: currentEdges,
        },
      }).unwrap();

      const description = response.pipeline_description;
      const blob = new Blob([description], {
        type: "text/plain",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${pipelineName || "pipeline"}.txt`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success("Pipeline description downloaded");
    } catch (error) {
      handleApiError(error, "Failed to generate pipeline description");
      console.error("Failed to generate description:", error);
    }
  };

  const handleImportDescriptionClick = async () => {
    if (!pipelineDescription.trim()) {
      toast.error("Pipeline description is empty");
      return;
    }

    setIsImporting(true);
    try {
      const result = await toGraph({
        pipelineDescription: {
          pipeline_description: pipelineDescription,
        },
      }).unwrap();

      // Import createGraphLayout dynamically
      const { createGraphLayout } = await import(
        "@/features/pipeline-editor/utils/graphLayout"
      );

      const nodesWithPositions = createGraphLayout(
        result.pipeline_graph.nodes.map((node) => ({
          id: node.id,
          type: node.type,
          data: node.data,
          position: { x: 0, y: 0 },
        })),
        result.pipeline_graph.edges,
      );

      const viewport: Viewport = {
        x: 0,
        y: 0,
        zoom: 1,
      };

      onGraphUpdate(
        nodesWithPositions,
        result.pipeline_graph.edges,
        viewport,
        true,
      );
      toast.success("Pipeline imported successfully");
      setImportDialogOpen(false);
      setPipelineDescription("");
    } catch (error) {
      handleApiError(error, "Failed to import pipeline");
      console.error("Failed to import pipeline:", error);
    } finally {
      setIsImporting(false);
    }
  };

  const handleOptimizePipeline = async () => {
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

      toast.info("Validating pipeline...");

      const validationStatus = await executeValidation({
        pipelineValidationInput: {
          pipeline_graph: pipelineGraph,
        },
      });

      if (!validationStatus.is_valid) {
        toast.error("Pipeline validation failed", {
          description: formatErrorMessage(validationStatus.error_message),
        });
        return;
      }

      await updateVariant({
        pipelineId,
        variantId,
        variantUpdate: {
          pipeline_graph: pipelineGraph,
        },
      }).unwrap();

      toast.info("Optimizing pipeline...");

      const optimizationStatus = await executeOptimization({
        pipelineId,
        variantId,
        pipelineRequestOptimize: {
          type: "optimize",
          parameters: {
            search_duration: 300,
            sample_duration: 10,
          },
        },
      });

      const optimizedGraph = optimizationStatus.optimized_pipeline_graph;

      if (!optimizedGraph) {
        toast.error("Optimization completed but no optimized graph available");
        return;
      }

      const applyOptimizedPipeline = async () => {
        toast.dismiss();

        const { createGraphLayout } = await import(
          "@/features/pipeline-editor/utils/graphLayout"
        );

        const nodesWithPositions = createGraphLayout(
          optimizedGraph.nodes.map((node) => ({
            id: node.id,
            type: node.type,
            data: node.data,
            position: { x: 0, y: 0 },
          })),
          optimizedGraph.edges,
        );

        const newEdges: ReactFlowEdge[] = optimizedGraph.edges.map((edge) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
        }));

        const viewport: Viewport = {
          x: 0,
          y: 0,
          zoom: 1,
        };

        onGraphUpdate(nodesWithPositions, newEdges, viewport, true);
        toast.success("Optimized pipeline applied");
      };

      toast.success("Pipeline optimization completed", {
        duration: Infinity,
        description: "Would you like to apply the optimized pipeline?",
        action: {
          label: "Apply",
          onClick: () => {
            applyOptimizedPipeline();
          },
        },
        cancel: {
          label: "Cancel",
          onClick: () => {
            toast.dismiss();
          },
        },
      });
    } catch (error) {
      handleApiError(error, "Failed to optimize pipeline");
      console.error("Failed to optimize pipeline:", error);
    }
  };

  return (
    <>
      <input
        id="import-pipeline-input"
        type="file"
        accept=".json"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) {
            const reader = new FileReader();
            reader.onload = (event) => {
              try {
                const content = event.target?.result as string;
                const parsedData = JSON.parse(content);
                onGraphUpdate(
                  parsedData.nodes ?? [],
                  parsedData.edges ?? [],
                  parsedData.viewport,
                  true,
                );
                toast.success("Pipeline imported successfully");
              } catch {
                toast.error("Failed to import pipeline", {
                  description: "Invalid file format",
                });
              }
            };
            reader.readAsText(file);
          }
          e.target.value = "";
        }}
      />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon">
            <MoreVertical className="w-5 h-5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            disabled={isReadOnly}
            className="flex items-center justify-between gap-2"
            onClick={() => {
              setEditVariantMode("edit");
              setEditVariantDialogOpen(true);
            }}
          >
            <div className="flex items-center gap-2">
              <PencilLine className="w-4 h-4" />
              Rename variant
            </div>
            {isReadOnly && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="pointer-events-auto">
                    <Lock className="h-4 w-4" />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">
                  Read-only variant cannot be renamed.
                </TooltipContent>
              </Tooltip>
            )}
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => {
              setEditVariantMode("create");
              setEditVariantDialogOpen(true);
            }}
          >
            <Save className="w-4 h-4" />
            Save as new variant
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={handleOptimizePipeline}
            disabled={
              isSimpleMode ||
              isReadOnly ||
              isValidating ||
              isOptimizing ||
              performanceTestJobId != null
            }
            className="flex items-center justify-between gap-2"
          >
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4" />
              Optimize pipeline
            </div>
            {(isSimpleMode || isReadOnly) && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="pointer-events-auto">
                    <Lock className="h-4 w-4" />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">
                  {isReadOnly
                    ? "Read-only variant cannot be modified."
                    : "Only available in advanced mode."}
                </TooltipContent>
              </Tooltip>
            )}
          </DropdownMenuItem>
          {isSimpleMode || isReadOnly ? (
            <DropdownMenuItem
              disabled
              className="flex items-center justify-between gap-2"
            >
              <div className="flex items-center gap-2">
                <Upload className="w-4 h-4" />
                Import pipeline
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="pointer-events-auto">
                    <Lock className="h-4 w-4" />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">
                  {isReadOnly
                    ? "Read-only variant cannot be modified."
                    : "Only available in advanced mode."}
                </TooltipContent>
              </Tooltip>
            </DropdownMenuItem>
          ) : (
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>
                <Upload className="w-4 h-4" />
                Import pipeline
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent>
                <DropdownMenuItem onClick={handleImportJson}>
                  <FileJson className="w-4 h-4" />
                  Import JSON File
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => {
                    setImportDialogOpen(true);
                  }}
                >
                  <Terminal className="w-4 h-4" />
                  Import GST Description
                </DropdownMenuItem>
              </DropdownMenuSubContent>
            </DropdownMenuSub>
          )}
          {isSimpleMode ? (
            <DropdownMenuItem
              disabled
              className="flex items-center justify-between gap-2"
            >
              <div className="flex items-center gap-2">
                <Download className="w-4 h-4" />
                Export pipeline
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="pointer-events-auto">
                    <Lock className="h-4 w-4" />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">
                  Only available in advanced mode.
                </TooltipContent>
              </Tooltip>
            </DropdownMenuItem>
          ) : (
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>
                <Download className="w-4 h-4" />
                Export pipeline
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent>
                <DropdownMenuItem onClick={handleExportJson}>
                  <FileJson className="w-4 h-4" />
                  Export as JSON
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={handleExportDescription}
                  disabled={isExportingDescription}
                >
                  <Terminal className="w-4 h-4" />
                  {isExportingDescription
                    ? "Generating..."
                    : "Export as GST Description"}
                </DropdownMenuItem>
              </DropdownMenuSubContent>
            </DropdownMenuSub>
          )}
          <DropdownMenuItem
            variant="destructive"
            disabled={isReadOnly}
            className="flex items-center justify-between gap-2"
            onClick={() => {
              if (variantsCount === 1) {
                setDeletePipelineDialogOpen(true);
              } else {
                setDeleteVariantDialogOpen(true);
              }
            }}
          >
            <div className="flex items-center gap-2">
              <Trash2 className="w-4 h-4 text-destructive" />
              {variantsCount === 1 ? "Delete pipeline" : "Delete variant"}
            </div>
            {isReadOnly && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="pointer-events-auto">
                    <Lock className="h-4 w-4" />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">
                  Read-only variant cannot be deleted.
                </TooltipContent>
              </Tooltip>
            )}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
        <DialogContent className="!max-w-6xl">
          <DialogHeader>
            <DialogTitle>Import Pipeline Description</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label
                htmlFor="file-upload"
                className="block text-sm font-medium mb-2"
              >
                Upload file with Pipeline Description (.txt)
              </label>
              <input
                id="file-upload"
                type="file"
                accept=".txt"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  const reader = new FileReader();
                  reader.onload = (event) => {
                    const content = event.target?.result as string;
                    setPipelineDescription(content);
                  };
                  reader.readAsText(file);
                }}
                className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-primary file:text-primary-foreground hover:file:bg-primary/90"
              />
            </div>

            <div>
              <label
                htmlFor="pipeline-description"
                className="block text-sm font-medium mb-2"
              >
                Pipeline Description
              </label>
              <textarea
                id="pipeline-description"
                value={pipelineDescription}
                onChange={(e) => setPipelineDescription(e.target.value)}
                placeholder="Paste or upload your pipeline description here..."
                className="w-full h-64 p-3 border rounded-md resize-none font-mono text-sm"
              />
            </div>

            <div className="flex justify-end gap-2">
              <button
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
                onClick={() => {
                  setImportDialogOpen(false);
                  setPipelineDescription("");
                }}
              >
                Cancel
              </button>
              <button
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={handleImportDescriptionClick}
                disabled={isImporting || !pipelineDescription.trim()}
              >
                {isImporting ? "Importing..." : "Import"}
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <EditVariantDialog
        mode={editVariantMode}
        pipelineId={pipelineId}
        variantId={variantId}
        currentVariantName={variantName}
        currentNodes={currentNodes}
        currentEdges={currentEdges}
        isSimpleMode={isSimpleMode}
        open={editVariantDialogOpen}
        onOpenChange={setEditVariantDialogOpen}
        onSuccess={() => {
          if (editVariantMode === "edit") {
            onVariantRenamed?.();
          }
        }}
      />

      <DeletePipelineVariantDialog
        open={deleteVariantDialogOpen}
        onOpenChange={setDeleteVariantDialogOpen}
        pipelineId={pipelineId}
        variantId={variantId}
        variantName={variantName}
        onSuccess={onVariantDeleted}
      />

      <DeletePipelineDialog
        open={deletePipelineDialogOpen}
        onOpenChange={setDeletePipelineDialogOpen}
        pipeline={pipeline}
        onSuccess={onVariantDeleted}
      />
    </>
  );
};
