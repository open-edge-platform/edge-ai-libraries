import type { ReactNode } from "react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Upload } from "lucide-react";
import { useNavigate } from "react-router";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog.tsx";
import {
  useCreatePipelineMutation,
  useGetValidationJobStatusQuery,
  useToGraphMutation,
  useValidatePipelineMutation,
} from "@/api/api.generated.ts";
import { toast } from "sonner";
import {
  handleApiError,
  handleAsyncJobError,
  isAsyncJobError,
} from "@/lib/apiUtils.ts";
import { Button } from "@/components/ui/button.tsx";
import { Input } from "@/components/ui/input.tsx";
import { Textarea } from "@/components/ui/textarea.tsx";
import { Field, FieldError, FieldLabel } from "@/components/ui/field.tsx";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupText,
} from "@/components/ui/input-group.tsx";
import { Separator } from "@/components/ui/separator.tsx";
import { useAsyncJob } from "@/hooks/useAsyncJob";
import {
  type CreatePipelineFormData,
  createPipelineSchema,
} from "./pipelineSchemas";
import { PipelineTagsCombobox } from "./PipelineTagsCombobox";

type CreatePipelineDialogProps = {
  children: ReactNode;
};

export const CreatePipelineDialog = ({
  children,
}: CreatePipelineDialogProps) => {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    watch,
    setValue,
    trigger,
  } = useForm<CreatePipelineFormData>({
    resolver: zodResolver(createPipelineSchema),
    defaultValues: {
      name: "",
      description: "",
      tags: [],
      variantName: "",
      pipelineDescription: "",
    },
  });

  const tags = watch("tags");

  const [createPipeline, { isLoading: isCreating }] =
    useCreatePipelineMutation();
  const [toGraph, { isLoading: isConverting }] = useToGraphMutation();

  const { execute: validatePipeline, isLoading: isValidating } = useAsyncJob({
    asyncJobHook: useValidatePipelineMutation,
    statusCheckHook: useGetValidationJobStatusQuery,
  });

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      setValue("pipelineDescription", content);
      trigger("pipelineDescription");
    };
    reader.readAsText(file);
  };

  const onSubmit = async (data: CreatePipelineFormData) => {
    try {
      // Step 1: Convert description to graph
      const graphResponse = await toGraph({
        pipelineDescription: {
          pipeline_description: data.pipelineDescription,
        },
      }).unwrap();

      // Step 2: Validate pipeline graph
      await validatePipeline({
        pipelineValidationInput: {
          pipeline_graph: graphResponse.pipeline_graph,
        },
      });

      // Step 3: Create pipeline
      const variantName = data.variantName.trim() || "default";
      const response = await createPipeline({
        pipelineDefinition: {
          name: data.name.trim(),
          description: data.description.trim(),
          source: "USER_CREATED",
          tags: data.tags.length > 0 ? data.tags : undefined,
          variants: [
            {
              name: variantName,
              pipeline_graph: graphResponse.pipeline_graph,
              pipeline_graph_simple: graphResponse.pipeline_graph_simple,
            },
          ],
        },
      }).unwrap();

      if (response.id) {
        setOpen(false);
        reset();
        toast.success("Pipeline created successfully");
        navigate(`/pipelines/${response.id}/${variantName}`);
      }
    } catch (error) {
      if (isAsyncJobError(error)) {
        handleAsyncJobError(error, "Pipeline validation");
      } else {
        handleApiError(error, "Failed to process pipeline");
      }
      console.error("Failed to process pipeline:", error);
    }
  };

  const isProcessing = isConverting || isValidating || isCreating;

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        setOpen(isOpen);
        if (!isOpen) {
          reset();
        }
      }}
    >
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent
        className="max-w-6xl!"
        onInteractOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Create Pipeline</DialogTitle>
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

          <Field>
            <FieldLabel htmlFor="variant-name">Variant Name</FieldLabel>
            <Input
              id="variant-name"
              type="text"
              {...register("variantName")}
              placeholder="default"
            />
            <FieldError
              errors={errors.variantName ? [errors.variantName] : undefined}
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="file-upload">
              Upload file with Pipeline Description (.txt)
            </FieldLabel>
            <InputGroup>
              <InputGroupAddon
                className="cursor-pointer bg-accent"
                onClick={() => document.getElementById("file-upload")?.click()}
              >
                <InputGroupText className="cursor-pointer">
                  <Upload />
                  <span className="pr-3">Choose file</span>
                </InputGroupText>
              </InputGroupAddon>
              <Separator orientation="vertical" className="h-6" />
              <input
                id="file-upload"
                type="file"
                accept=".txt"
                onChange={handleFileUpload}
                className="flex-1 bg-transparent text-sm file:hidden px-3 cursor-pointer"
                onClick={() => document.getElementById("file-upload")?.click()}
              />
            </InputGroup>
          </Field>

          <Field>
            <FieldLabel htmlFor="pipeline-description">
              Pipeline Description
            </FieldLabel>
            <Textarea
              id="pipeline-description"
              {...register("pipelineDescription")}
              placeholder="Paste or upload your pipeline description here..."
              className="h-64 resize-none"
            />
            <FieldError
              errors={
                errors.pipelineDescription
                  ? [errors.pipelineDescription]
                  : undefined
              }
            />
          </Field>

          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSubmit(onSubmit)} disabled={isProcessing}>
              {isProcessing ? "Processing..." : "Create"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
