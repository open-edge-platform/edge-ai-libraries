import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  type Edge as ReactFlowEdge,
  type Node as ReactFlowNode,
} from "@xyflow/react";
import { toast } from "sonner";
import { isApiError } from "@/lib/apiUtils";
import { useUpdateVariantMutation } from "@/api/api.generated";

interface ViewModeSwitcherProps {
  pipelineId: string;
  variant: string;
  isPredefined: boolean;
  isSimpleMode: boolean;
  currentNodes: ReactFlowNode[];
  currentEdges: ReactFlowEdge[];
  onModeChange: (isSimple: boolean) => void;
  onTransitionStart: () => void;
  onTransitionEnd: () => void;
  onClearGraph: () => void;
  onRefetch: () => Promise<unknown>;
  onEditorKeyChange: () => void;
}

const ViewModeSwitcher = ({
  pipelineId,
  variant,
  isPredefined,
  isSimpleMode,
  currentNodes,
  currentEdges,
  onModeChange,
  onTransitionStart,
  onTransitionEnd,
  onClearGraph,
  onRefetch,
  onEditorKeyChange,
}: ViewModeSwitcherProps) => {
  const [updateVariant] = useUpdateVariantMutation();

  const handleModeSwitch = async (checked: boolean) => {
    onTransitionStart();

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

      // TODO: for predefined we skip save, so user is not able to make any changes for
      // predefined pipeline or wont be able to switch mode or run pipeline
      if (!isPredefined) {
        await updateVariant({
          pipelineId,
          variantId: variant,
          variantUpdate: isSimpleMode
            ? { pipeline_graph_simple: graphData }
            : { pipeline_graph: graphData },
        }).unwrap();
      }

      // Force refetch pipeline data
      await onRefetch();

      onModeChange(!checked);
      onClearGraph();
      onEditorKeyChange();

      setTimeout(() => onTransitionEnd(), 100);
    } catch (error) {
      const errorMessage = isApiError(error)
        ? error.data.message
        : "Unknown error";
      toast.error("Failed to update pipeline", {
        description: errorMessage,
      });
      onTransitionEnd();
      console.error("Failed to update pipeline:", error);
    }
  };

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <label className="bg-background p-2 flex items-center gap-2 cursor-pointer">
          <Switch checked={!isSimpleMode} onCheckedChange={handleModeSwitch} />
          <span className="text-sm font-medium">Advanced View</span>
        </label>
      </TooltipTrigger>
      <TooltipContent side="bottom">
        <p>Display all DLStreamer pipeline elements</p>
      </TooltipContent>
    </Tooltip>
  );
};

export default ViewModeSwitcher;
