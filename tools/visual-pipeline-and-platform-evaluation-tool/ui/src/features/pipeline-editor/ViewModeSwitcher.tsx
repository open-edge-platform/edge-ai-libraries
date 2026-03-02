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
import { handleApiError } from "@/lib/apiUtils";
import { useUpdateVariantMutation } from "@/api/api.generated";
import { UnsavedChangesDialog } from "@/components/shared/UnsavedChangesDialog";
import { useState } from "react";

interface ViewModeSwitcherProps {
  pipelineId: string;
  variant: string;
  isPredefined: boolean;
  isSimpleMode: boolean;
  currentNodes: ReactFlowNode[];
  currentEdges: ReactFlowEdge[];
  hasUnsavedChanges: boolean;
  onModeChange: (isSimple: boolean) => void;
  onTransitionStart: () => void;
  onTransitionEnd: () => void;
  onClearGraph: () => void;
  onRefetch: () => Promise<unknown>;
  onEditorKeyChange: () => void;
  onResetHistory: () => void;
}

const ViewModeSwitcher = ({
  pipelineId,
  variant,
  isPredefined,
  isSimpleMode,
  currentNodes,
  currentEdges,
  hasUnsavedChanges,
  onModeChange,
  onTransitionStart,
  onTransitionEnd,
  onClearGraph,
  onRefetch,
  onEditorKeyChange,
  onResetHistory,
}: ViewModeSwitcherProps) => {
  const [updateVariant] = useUpdateVariantMutation();
  const [showUnsavedDialog, setShowUnsavedDialog] = useState(false);
  const [pendingModeChange, setPendingModeChange] = useState<boolean | null>(
    null,
  );

  const performModeSwitch = async (checked: boolean, skipSave = false) => {
    onTransitionStart();

    try {
      // Only save current state if not skipping (i.e., when not discarding changes)
      if (!skipSave && !isPredefined) {
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
      onResetHistory();

      setTimeout(() => onTransitionEnd(), 100);
    } catch (error) {
      handleApiError(error, "Failed to update pipeline");
      onTransitionEnd();
      console.error("Failed to update pipeline:", error);
    }
  };

  const handleModeSwitch = (checked: boolean) => {
    if (hasUnsavedChanges) {
      setPendingModeChange(checked);
      setShowUnsavedDialog(true);
    } else {
      performModeSwitch(checked);
    }
  };

  const handleDiscardChanges = () => {
    setShowUnsavedDialog(false);
    if (pendingModeChange !== null) {
      performModeSwitch(pendingModeChange, true);
      setPendingModeChange(null);
    }
  };

  const handleCancelDialog = () => {
    setShowUnsavedDialog(false);
    setPendingModeChange(null);
  };

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <label className="bg-background p-2 flex items-center gap-2 cursor-pointer">
            <Switch
              checked={!isSimpleMode}
              onCheckedChange={handleModeSwitch}
            />
            <span className="text-sm font-medium">Advanced View</span>
          </label>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          <p>Display all DLStreamer pipeline elements</p>
        </TooltipContent>
      </Tooltip>

      <UnsavedChangesDialog
        open={showUnsavedDialog}
        onOpenChange={handleCancelDialog}
        onDiscard={handleDiscardChanges}
        title="Unsaved Changes"
        description="You have unsaved changes to this pipeline. Switching view modes will discard these changes. Do you want to continue?"
      />
    </>
  );
};

export default ViewModeSwitcher;
