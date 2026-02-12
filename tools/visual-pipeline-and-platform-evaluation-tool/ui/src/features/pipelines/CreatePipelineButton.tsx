import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useTheme } from "next-themes";
import { Plus, Upload } from "lucide-react";
import { useNavigate } from "react-router";
import { useAppSelector } from "@/store/hooks";
import { selectPipelines } from "@/store/reducers/pipelines";
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
import { isApiError, isAsyncJobError } from "@/lib/apiUtils.ts";
import { Button } from "@/components/ui/button.tsx";
import { Input } from "@/components/ui/input.tsx";
import { Textarea } from "@/components/ui/textarea.tsx";
import {
  Combobox,
  ComboboxChip,
  ComboboxChips,
  ComboboxChipsInput,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox.tsx";
import { Field, FieldError, FieldLabel } from "@/components/ui/field.tsx";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupText,
} from "@/components/ui/input-group.tsx";
import { Separator } from "@/components/ui/separator.tsx";
import { usePipelineTagColors } from "@/hooks/usePipelineTagColors";
import { useAsyncJob } from "@/hooks/useAsyncJob";

const formSchema = z.object({
  name: z
    .string()
    .min(3, "Name must be at least 3 characters")
    .max(20, "Name must be at most 20 characters"),
  description: z.string().min(1, "Description is required"),
  tags: z.array(z.string()).min(1, "At least one tag is required"),
  variantName: z.union([
    z.string().min(3, "Variant name must be at least 3 characters"),
    z.literal(""),
  ]),
  pipelineDescription: z.string().min(1, "Pipeline description is required"),
});

type FormData = z.infer<typeof formSchema>;

export const CreatePipelineButton = () => {
  const { theme } = useTheme();
  const navigate = useNavigate();
  const pipelines = useAppSelector(selectPipelines);
  const { tagColorMap, availableTags } = usePipelineTagColors(pipelines);
  const [open, setOpen] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    watch,
    setValue,
    trigger,
  } = useForm<FormData>({
    resolver: zodResolver(formSchema),
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

  const onSubmit = async (data: FormData) => {
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
        if (error.state === "ERROR") {
          const errors = error.error_message?.join(", ") ?? "Validation error";
          toast.error("Pipeline validation error", {
            description: errors,
          });
        } else if (error.state === "ABORTED") {
          const errors =
            error.error_message?.join(", ") ?? "Validation aborted";
          toast.error("Pipeline validation aborted", {
            description: errors,
          });
        }
      } else if (isApiError(error)) {
        toast.error("Failed to process pipeline", {
          description: error.data.message,
        });
      } else {
        toast.error("Failed to process pipeline", {
          description: "Unknown error",
        });
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
      <DialogTrigger asChild>
        <button className="w-full h-full min-h-[200px] border-2 border-dashed border-gray-300 dark:border-gray-700 hover:border-classic-blue dark:hover:border-energy-blue hover:bg-blue-50 dark:hover:bg-energy-blue/5 transition-all flex flex-col items-center justify-center gap-3 text-carbon-tint-1 dark:text-gray-400 hover:text-classic-blue  dark:hover:text-energy-blue">
          <Plus className="w-12 h-12" />
          <span className="text-lg font-medium">Create Pipeline</span>
        </button>
      </DialogTrigger>
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
            <Combobox
              value={tags}
              onValueChange={(newTags) => {
                setValue("tags", newTags);
                trigger("tags");
              }}
              multiple
            >
              <ComboboxChips>
                {tags.map((tag) => {
                  const color = tagColorMap.get(tag);
                  return (
                    <ComboboxChip
                      key={tag}
                      style={
                        color
                          ? {
                              backgroundColor:
                                theme === "dark"
                                  ? `var(--${color})`
                                  : `color-mix(in oklch, var(--${color}) 50%, white)`,
                            }
                          : undefined
                      }
                    >
                      {tag}
                    </ComboboxChip>
                  );
                })}
                <ComboboxChipsInput
                  placeholder="Add tags..."
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && e.currentTarget.value) {
                      e.preventDefault();
                      const newTag = e.currentTarget.value.trim();
                      if (newTag && !tags.includes(newTag)) {
                        setValue("tags", [...tags, newTag]);
                        trigger("tags");
                        e.currentTarget.value = "";
                      }
                    }
                  }}
                />
              </ComboboxChips>
              <ComboboxContent>
                <ComboboxList>
                  {availableTags.length > 0 ? (
                    availableTags.map((tag) => (
                      <ComboboxItem key={tag} value={tag}>
                        {tag}
                      </ComboboxItem>
                    ))
                  ) : (
                    <ComboboxEmpty>No tags available.</ComboboxEmpty>
                  )}
                </ComboboxList>
              </ComboboxContent>
            </Combobox>
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
