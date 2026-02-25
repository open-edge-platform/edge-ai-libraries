import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog.tsx";
import {
  type Pipeline,
  useCreatePipelineMutation,
} from "@/api/api.generated.ts";
import { toast } from "sonner";
import { handleApiError } from "@/lib/apiUtils.ts";
import { Button } from "@/components/ui/button.tsx";
import { Input } from "@/components/ui/input.tsx";
import { Field, FieldError, FieldLabel } from "@/components/ui/field.tsx";
import {
  type PipelineMetadataFormData,
  pipelineMetadataSchema,
} from "./pipelineSchemas";
import { PipelineTagsCombobox } from "./PipelineTagsCombobox";

type DuplicatePipelineDialogProps = {
  pipeline: Pipeline;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
};

export const DuplicatePipelineDialog = ({
  pipeline,
  open,
  onOpenChange,
  onSuccess,
}: DuplicatePipelineDialogProps) => {
  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    watch,
    setValue,
    trigger,
  } = useForm<PipelineMetadataFormData>({
    resolver: zodResolver(pipelineMetadataSchema),
    defaultValues: {
      name: "",
      description: pipeline.description,
      tags: pipeline.tags ?? [],
    },
  });

  const tags = watch("tags");

  const [createPipeline, { isLoading: isCreating }] =
    useCreatePipelineMutation();

  const onSubmit = async (data: PipelineMetadataFormData) => {
    try {
      await createPipeline({
        pipelineDefinition: {
          name: data.name.trim(),
          description: data.description.trim(),
          source: "USER_CREATED",
          tags: data.tags.length > 0 ? data.tags : undefined,
          variants: pipeline.variants.map((variant) => ({
            name: variant.name,
            pipeline_graph: variant.pipeline_graph,
            pipeline_graph_simple: variant.pipeline_graph_simple,
          })),
        },
      }).unwrap();

      onOpenChange(false);
      reset();
      toast.success("Pipeline duplicated successfully");
      onSuccess?.();
    } catch (error) {
      handleApiError(error, "Failed to duplicate pipeline");
      console.error("Failed to duplicate pipeline:", error);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        onOpenChange(isOpen);
        if (!isOpen) {
          reset({
            name: "",
            description: pipeline.description,
            tags: pipeline.tags ?? [],
          });
        }
      }}
    >
      <DialogContent
        className="max-w-6xl! top-[20%] translate-y-0"
        onInteractOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Duplicate Pipeline</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Field>
            <FieldLabel htmlFor="name">Name</FieldLabel>
            <Input
              id="name"
              type="text"
              {...register("name")}
              placeholder="Enter new pipeline name..."
            />
            <FieldError errors={errors.name ? [errors.name] : undefined} />
          </Field>

          <Field>
            <FieldLabel htmlFor="description">Description</FieldLabel>
            <Input
              id="description"
              type="text"
              {...register("description")}
              placeholder="Enter pipeline description..."
            />
            <FieldError
              errors={errors.description ? [errors.description] : undefined}
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="tags">Tags</FieldLabel>
            <PipelineTagsCombobox
              value={tags}
              onChange={(newTags) => {
                setValue("tags", newTags);
                trigger("tags");
              }}
            />
            <FieldError errors={errors.tags ? [errors.tags] : undefined} />
          </Field>

          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={handleSubmit(onSubmit)} disabled={isCreating}>
              {isCreating ? "Duplicating..." : "Duplicate"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
