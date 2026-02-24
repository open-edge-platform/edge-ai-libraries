import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "react-router";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog.tsx";
import {
  type PipelineGraph,
  useConvertAdvancedToSimpleMutation,
  useConvertSimpleToAdvancedMutation,
  useCreateVariantMutation,
} from "@/api/api.generated.ts";
import { toast } from "sonner";
import { isApiError } from "@/lib/apiUtils.ts";
import { Button } from "@/components/ui/button.tsx";
import { Input } from "@/components/ui/input.tsx";
import { Field, FieldError, FieldLabel } from "@/components/ui/field.tsx";
import {
  type Edge as ReactFlowEdge,
  type Node as ReactFlowNode,
} from "@xyflow/react";
import { type NewVariantFormData, newVariantSchema } from "./pipelineSchemas";

type NewVariantDialogProps = {
  pipelineId: string;
  variantId: string;
  currentNodes: ReactFlowNode[];
  currentEdges: ReactFlowEdge[];
  isSimpleMode: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
};

export const NewVariantDialog = ({
  pipelineId,
  variantId,
  currentNodes,
  currentEdges,
  isSimpleMode,
  open,
  onOpenChange,
  onSuccess,
}: NewVariantDialogProps) => {
  const navigate = useNavigate();
  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<NewVariantFormData>({
    resolver: zodResolver(newVariantSchema),
    defaultValues: {
      name: "",
    },
  });

  const [createVariant, { isLoading: isCreating }] = useCreateVariantMutation();
  const [convertSimpleToAdvanced] = useConvertSimpleToAdvancedMutation();
  const [convertAdvancedToSimple] = useConvertAdvancedToSimpleMutation();

  const onSubmit = async (data: NewVariantFormData) => {
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

      let advancedGraph: PipelineGraph;
      let simpleGraph: PipelineGraph;

      if (isSimpleMode) {
        advancedGraph = await convertSimpleToAdvanced({
          pipelineId,
          variantId,
          pipelineGraph,
        }).unwrap();
        simpleGraph = pipelineGraph;
      } else {
        const convertedSimple = await convertAdvancedToSimple({
          pipelineId,
          variantId,
          pipelineGraph,
        }).unwrap();
        advancedGraph = pipelineGraph;
        simpleGraph = convertedSimple;
      }

      const newVariant = await createVariant({
        pipelineId,
        variantCreate: {
          name: data.name.trim(),
          pipeline_graph: advancedGraph,
          pipeline_graph_simple: simpleGraph,
        },
      }).unwrap();

      onOpenChange(false);
      reset();
      toast.success("Variant created successfully");
      onSuccess?.();

      navigate(`/pipelines/${pipelineId}/${newVariant.id}`);
    } catch (error) {
      const errorMessage = isApiError(error)
        ? error.data.message
        : "Unknown error";
      toast.error(`Failed to create variant: ${errorMessage}`);
      console.error("Failed to create variant:", error);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        onOpenChange(isOpen);
        if (!isOpen) {
          reset();
        }
      }}
    >
      <DialogContent
        className="max-w-md top-[20%] translate-y-0"
        onInteractOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Save as New Variant</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Field>
            <FieldLabel htmlFor="name">Variant Name</FieldLabel>
            <Input
              id="name"
              type="text"
              {...register("name")}
              placeholder="Enter variant name..."
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  handleSubmit(onSubmit)();
                }
              }}
            />
            <FieldError errors={errors.name ? [errors.name] : undefined} />
          </Field>

          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={handleSubmit(onSubmit)} disabled={isCreating}>
              {isCreating ? "Creating..." : "Create"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
