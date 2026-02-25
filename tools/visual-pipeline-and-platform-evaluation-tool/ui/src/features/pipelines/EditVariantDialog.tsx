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
  useUpdateVariantMutation,
} from "@/api/api.generated.ts";
import { toast } from "sonner";
import { handleApiError } from "@/lib/apiUtils.ts";
import { Button } from "@/components/ui/button.tsx";
import { Input } from "@/components/ui/input.tsx";
import { Field, FieldError, FieldLabel } from "@/components/ui/field.tsx";
import {
  type Edge as ReactFlowEdge,
  type Node as ReactFlowNode,
} from "@xyflow/react";
import { type NewVariantFormData, newVariantSchema } from "./pipelineSchemas";
import { useEffect } from "react";

type EditVariantDialogProps = {
  mode: "create" | "edit";
  pipelineId: string;
  variantId: string;
  currentVariantName?: string;
  currentNodes: ReactFlowNode[];
  currentEdges: ReactFlowEdge[];
  isSimpleMode: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
};

export const EditVariantDialog = ({
  mode,
  pipelineId,
  variantId,
  currentVariantName = "",
  currentNodes,
  currentEdges,
  isSimpleMode,
  open,
  onOpenChange,
  onSuccess,
}: EditVariantDialogProps) => {
  const navigate = useNavigate();
  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    setValue,
  } = useForm<NewVariantFormData>({
    resolver: zodResolver(newVariantSchema),
    defaultValues: {
      name: "",
    },
  });

  const [createVariant, { isLoading: isCreating }] = useCreateVariantMutation();
  const [updateVariant, { isLoading: isUpdating }] = useUpdateVariantMutation();
  const [convertSimpleToAdvanced] = useConvertSimpleToAdvancedMutation();
  const [convertAdvancedToSimple] = useConvertAdvancedToSimpleMutation();

  useEffect(() => {
    if (mode === "edit" && open) {
      setValue("name", currentVariantName);
    } else if (mode === "create" && open) {
      setValue("name", "");
    }
  }, [mode, open, currentVariantName, setValue]);

  const onSubmit = async (data: NewVariantFormData) => {
    try {
      if (mode === "edit") {
        await updateVariant({
          pipelineId,
          variantId,
          variantUpdate: {
            name: data.name.trim(),
          },
        }).unwrap();

        onOpenChange(false);
        reset();
        toast.success("Variant renamed successfully");
        onSuccess?.();
      } else {
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
      }
    } catch (error) {
      handleApiError(
        error,
        `Failed to ${mode === "edit" ? "rename" : "create"} variant`,
      );
      console.error(
        `Failed to ${mode === "edit" ? "rename" : "create"} variant:`,
        error,
      );
    }
  };

  const isLoading = mode === "create" ? isCreating : isUpdating;

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
          <DialogTitle>
            {mode === "edit" ? "Rename Variant" : "Save as New Variant"}
          </DialogTitle>
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
            <Button onClick={handleSubmit(onSubmit)} disabled={isLoading}>
              {isLoading
                ? mode === "edit"
                  ? "Renaming..."
                  : "Creating..."
                : mode === "edit"
                  ? "Rename"
                  : "Create"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
