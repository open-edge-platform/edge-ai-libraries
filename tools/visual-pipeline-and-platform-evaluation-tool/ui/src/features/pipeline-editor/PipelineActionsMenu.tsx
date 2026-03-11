import { useEffect, useState } from "react";
import {
  useToDescriptionMutation,
  useToGraphMutation,
  useValidatePipelineMutation,
  useOptimizeVariantMutation,
  useGetValidationJobStatusQuery,
  useGetOptimizationJobStatusQuery,
  useUpdatePipelineMutation,
} from "@/api/api.generated";
import {
  type Edge as ReactFlowEdge,
  type Node as ReactFlowNode,
  type Viewport,
} from "@xyflow/react";
import {
  Download,
  FileJson,
  MoreVertical,
  Save,
  Terminal,
  Trash2,
  Upload,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { isApiError } from "@/lib/apiUtils";
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
import { NewVariantDialog } from "@/features/pipelines/NewVariantDialog";

interface PipelineActionsMenuProps {
  pipelineId: string;
  variant: string;
  currentNodes: ReactFlowNode[];
  currentEdges: ReactFlowEdge[];
  currentViewport?: Viewport;
  pipelineName: string;
  isSimpleMode: boolean;
  performanceTestJobId: string | null;
  onGraphUpdate: (
    nodes: ReactFlowNode[],
    edges: ReactFlowEdge[],
    viewport: Viewport,
    shouldFitView: boolean,
  ) => void;
}

export const PipelineActionsMenu = ({
  pipelineId,
  variant,
  currentNodes,
  currentEdges,
  currentViewport,
  pipelineName,
  isSimpleMode,
  performanceTestJobId,
  onGraphUpdate,
}: PipelineActionsMenuProps) => {
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [saveVariantDialogOpen, setSaveVariantDialogOpen] = useState(false);
  const [pipelineDescription, setPipelineDescription] = useState("");
  const [isImporting, setIsImporting] = useState(false);
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [validationJobId, setValidationJobId] = useState<string | null>(null);
  const [optimizationJobId, setOptimizationJobId] = useState<string | null>(
    null,
  );
  const [pendingOptimizationNodes, setPendingOptimizationNodes] = useState<
    ReactFlowNode[]
  >([]);
  const [pendingOptimizationEdges, setPendingOptimizationEdges] = useState<
    ReactFlowEdge[]
  >([]);

  const [toDescription, { isLoading: isExportingDescription }] =
    useToDescriptionMutation();
  const [toGraph] = useToGraphMutation();
  const [validatePipeline] = useValidatePipelineMutation();
  const [optimizePipeline] = useOptimizeVariantMutation();
  const [updatePipeline] = useUpdatePipelineMutation();

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
      const errorMessage = isApiError(error)
        ? error.data.message
        : "Unknown error";
      toast.error("Failed to generate pipeline description", {
        description: errorMessage,
      });
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
      const errorMessage = isApiError(error)
        ? error.data.message
        : "Unknown error";
      toast.error("Failed to import pipeline", {
        description: errorMessage,
      });
      console.error("Failed to import pipeline:", error);
    } finally {
      setIsImporting(false);
    }
  };

  const handleOptimizePipeline = async () => {
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

  // Handle validation errors
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

  // Handle optimization errors
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

  // Handle validation completion
  useEffect(() => {
    if (!validationJobId) return;

    const handleOptimizeAfterValidation = async () => {
      try {
        await updatePipeline({
          pipelineId,
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
          pipelineId,
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
    pipelineId,
    pendingOptimizationNodes,
    pendingOptimizationEdges,
    updatePipeline,
    optimizePipeline,
  ]);

  // Handle optimization completion
  useEffect(() => {
    const applyOptimizedPipeline = (optimizedGraph: {
      nodes: { id: string; type: string; data: { [key: string]: string } }[];
      edges: { id: string; source: string; target: string }[];
    }) => {
      toast.dismiss();

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

      const viewport: Viewport = {
        x: 0,
        y: 0,
        zoom: 1,
      };

      onGraphUpdate(newNodes, newEdges, viewport, true);
      setPendingOptimizationNodes([]);
      setPendingOptimizationEdges([]);
      toast.success("Optimized pipeline applied");
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
      setPendingOptimizationNodes([]);
      setPendingOptimizationEdges([]);
    }
  }, [optimizationStatus, onGraphUpdate]);

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
              } catch (error) {
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
            onClick={handleOptimizePipeline}
            disabled={isOptimizing || performanceTestJobId != null}
          >
            <Zap className="w-4 h-4" />
            Optimize pipeline
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => {
              setSaveVariantDialogOpen(true);
            }}
          >
            <Save className="w-4 h-4" />
            Save as new variant
          </DropdownMenuItem>
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
          <DropdownMenuItem
            variant="destructive"
            onClick={() => {
              toast.info("Delete variant - Not yet implemented");
            }}
          >
            <Trash2 className="w-4 h-4" />
            Delete variant
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

      <NewVariantDialog
        pipelineId={pipelineId}
        variantId={variant}
        currentNodes={currentNodes}
        currentEdges={currentEdges}
        isSimpleMode={isSimpleMode}
        open={saveVariantDialogOpen}
        onOpenChange={setSaveVariantDialogOpen}
      />
    </>
  );
};
