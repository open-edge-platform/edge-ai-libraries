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
  useUpdatePipelineMutation,
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

type EditPipelineDialogProps = {
  pipeline: Pipeline;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
};

export const EditPipelineDialog = ({
  pipeline,
  open,
  onOpenChange,
  onSuccess,
}: EditPipelineDialogProps) => {
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
      name: pipeline.name,
      description: pipeline.description,
      tags: pipeline.tags ?? [],
    },
  });

  const tags = watch("tags");

  const [updatePipeline, { isLoading: isUpdating }] =
    useUpdatePipelineMutation();

  const onSubmit = async (data: PipelineMetadataFormData) => {
    try {
      await updatePipeline({
        pipelineId: pipeline.id,
        pipelineUpdate: {
          name: data.name.trim(),
          description: data.description.trim(),
          tags: data.tags.length > 0 ? data.tags : undefined,
        },
      }).unwrap();

      onOpenChange(false);
      reset();
      toast.success("Pipeline updated successfully");
      onSuccess?.();
    } catch (error) {
      handleApiError(error, "Failed to update pipeline");
      console.error("Failed to update pipeline:", error);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        onOpenChange(isOpen);
        if (!isOpen) {
          reset({
            name: pipeline.name,
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
          <DialogTitle>Edit Pipeline</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Field>
            <FieldLabel htmlFor="name">Name</FieldLabel>
            <Input
              id="name"
              type="text"
              {...register("name")}
              placeholder="Enter pipeline name..."
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
            <Button onClick={handleSubmit(onSubmit)} disabled={isUpdating}>
              {isUpdating ? "Updating..." : "Update"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
