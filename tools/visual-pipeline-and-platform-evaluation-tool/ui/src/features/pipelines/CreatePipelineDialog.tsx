import type { ReactNode } from "react";
import { useRef, useState } from "react";
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
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs.tsx";
import {
  useCreatePipelineMutation,
  useGetPipelineTemplatesQuery,
  useGetValidationJobStatusQuery,
  useGetVideosQuery,
  useToGraphMutation,
  useValidatePipelineMutation,
  type Pipeline,
  type PipelineGraph,
} from "@/api/api.generated.ts";
import { toast } from "sonner";
import {
  handleApiError,
  handleAsyncJobError,
  isAsyncJobError,
} from "@/lib/apiUtils.ts";
import { useAppSelector } from "@/store/hooks.ts";
import { selectModels } from "@/store/reducers/models";
import { Button } from "@/components/ui/button.tsx";
import { Card } from "@/components/ui/card.tsx";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group.tsx";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select.tsx";
import {
  InteractiveStepper,
  InteractiveStepperContent,
  InteractiveStepperDescription,
  InteractiveStepperIndicator,
  InteractiveStepperItem,
  InteractiveStepperSeparator,
  InteractiveStepperTitle,
  InteractiveStepperTrigger,
  type IStepperMethods,
} from "@/components/ui/interactive-stepper.tsx";
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
import { isSupportedVideoFilename } from "@/lib/videoUtils.ts";

type CreatePipelineDialogProps = {
  children: ReactNode;
};

export const CreatePipelineDialog = ({
  children,
}: CreatePipelineDialogProps) => {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<Pipeline | null>(
    null,
  );
  const dialogContentRef = useRef<HTMLElement | null>(null);
  const stepperRef = useRef<HTMLDivElement & IStepperMethods>(null);

  const { data: templates, isLoading: isLoadingTemplates } =
    useGetPipelineTemplatesQuery();
  const { data: videos = [] } = useGetVideosQuery();
  const models = useAppSelector(selectModels);

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
      templateId: "",
      sourceFileName: "",
      detectionModel: "",
      classificationModel: "",
    },
  });

  const tags = watch("tags");

  const videoOptions = videos
    .filter((video) => isSupportedVideoFilename(video.filename))
    .map((video) => video.filename);

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

  const updateGraphNodesWithTemplateValues = (
    graph: PipelineGraph,
    data: CreatePipelineFormData,
  ): PipelineGraph => {
    if (!graph) return { nodes: [], edges: [] };

    return {
      ...graph,
      nodes: (graph.nodes ?? []).map((node) => {
        if (node.type === "filesrc") {
          return {
            ...node,
            data: {
              ...node.data,
              location: data.sourceFileName ?? "",
            },
          };
        }
        if (node.type === "source") {
          return {
            ...node,
            data: {
              ...node.data,
              source: data.sourceFileName ?? "",
            },
          };
        }
        if (node.type === "gvadetect") {
          return {
            ...node,
            data: {
              ...node.data,
              model: data.detectionModel ?? "",
            },
          };
        }
        if (node.type === "gvaclassify") {
          return {
            ...node,
            data: {
              ...node.data,
              model: data.classificationModel ?? "",
            },
          };
        }
        return node;
      }),
    };
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

  const onSubmitTemplate = async (data: CreatePipelineFormData) => {
    try {
      if (!selectedTemplate) return;

      const formData = {
        name: data.name,
        description: data.description,
        tags: data.tags,
      };

      const variants = (selectedTemplate.variants ?? []).map((variant) => ({
        ...variant,
        pipeline_graph: updateGraphNodesWithTemplateValues(
          variant.pipeline_graph,
          data,
        ),
        pipeline_graph_simple: updateGraphNodesWithTemplateValues(
          variant.pipeline_graph_simple,
          data,
        ),
      }));

      const response = await createPipeline({
        pipelineDefinition: {
          name: formData.name.trim(),
          description: formData.description.trim(),
          source: "USER_CREATED",
          tags: formData.tags.length > 0 ? formData.tags : undefined,
          variants: variants,
        },
      }).unwrap();

      if (response.id) {
        setOpen(false);
        reset();
        setSelectedTemplate(null);
        toast.success("Pipeline created successfully");
        const variantId = variants[0]?.id || "default";
        navigate(`/pipelines/${response.id}/${variantId}`);
      }
    } catch (error) {
      handleApiError(error, "Failed to create pipeline from template");
      console.error("Failed to create pipeline from template:", error);
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
        ref={(node) => {
          dialogContentRef.current = node;
        }}
        onInteractOutside={(e) => {
          const target = e.target;
          if (!(target instanceof HTMLElement)) {
            return;
          }

          if (target.closest('[data-slot="combobox-content"]')) {
            e.preventDefault();
          }
        }}
      >
        <DialogHeader>
          <DialogTitle>Create Pipeline</DialogTitle>
        </DialogHeader>
        <Tabs defaultValue="template" className="w-full">
          <TabsList className="w-full">
            <TabsTrigger value="template" className="flex-1">
              From Template
            </TabsTrigger>
            <TabsTrigger value="form" className="flex-1">
              From Description
            </TabsTrigger>
          </TabsList>

          <TabsContent value="form" className="space-y-4 mt-4">
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
                portalContainer={dialogContentRef}
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
                  onClick={() =>
                    document.getElementById("file-upload")?.click()
                  }
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
                  onClick={() =>
                    document.getElementById("file-upload")?.click()
                  }
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
          </TabsContent>

          <TabsContent value="template" className="space-y-4 mt-4">
            {isLoadingTemplates ? (
              <div className="flex items-center justify-center h-96">
                <p className="text-muted-foreground">Loading templates...</p>
              </div>
            ) : templates && templates.length > 0 ? (
              <div className="space-y-4">
                <Field>
                  <FieldLabel htmlFor="template-name">Name</FieldLabel>
                  <Input
                    id="template-name"
                    type="text"
                    {...register("name")}
                    placeholder="Enter pipeline name..."
                  />
                  <FieldError
                    errors={errors.name ? [errors.name] : undefined}
                  />
                </Field>

                <Field>
                  <FieldLabel htmlFor="template-description">
                    Description
                  </FieldLabel>
                  <Input
                    id="template-description"
                    type="text"
                    {...register("description")}
                    placeholder="Enter pipeline description..."
                  />
                  <FieldError
                    errors={
                      errors.description ? [errors.description] : undefined
                    }
                  />
                </Field>

                <Field>
                  <FieldLabel htmlFor="template-tags">Tags</FieldLabel>
                  <PipelineTagsCombobox
                    portalContainer={dialogContentRef}
                    value={tags}
                    onChange={(newTags) => {
                      setValue("tags", newTags);
                      trigger("tags");
                    }}
                  />
                  <FieldError
                    errors={errors.tags ? [errors.tags] : undefined}
                  />
                </Field>

                <Field>
                  <FieldLabel>Template</FieldLabel>
                  <InteractiveStepper
                    ref={stepperRef}
                    defaultValue={1}
                    orientation="horizontal"
                    className="w-full [&>div:first-child]:justify-center [&>div:first-child]:mx-auto [&>div:first-child]:max-w-max"
                  >
                    <InteractiveStepperItem className="w-72 gap-8">
                      <InteractiveStepperTrigger>
                        <InteractiveStepperIndicator />
                        <div className="text-center">
                          <InteractiveStepperTitle>
                            Select Template
                          </InteractiveStepperTitle>
                          <InteractiveStepperDescription>
                            Choose a pipeline template
                          </InteractiveStepperDescription>
                        </div>
                      </InteractiveStepperTrigger>
                      <InteractiveStepperSeparator />
                    </InteractiveStepperItem>

                    <InteractiveStepperItem className="w-72 gap-8">
                      <InteractiveStepperTrigger>
                        <InteractiveStepperIndicator />
                        <div className="text-center">
                          <InteractiveStepperTitle>
                            Configure Pipeline
                          </InteractiveStepperTitle>
                          <InteractiveStepperDescription>
                            Fill in required details
                          </InteractiveStepperDescription>
                        </div>
                      </InteractiveStepperTrigger>
                      <InteractiveStepperSeparator />
                    </InteractiveStepperItem>

                    <InteractiveStepperContent
                      step={1}
                      className="w-full min-w-0"
                    >
                      <div className="space-y-3 w-full">
                        <Field>
                          <FieldLabel>Select a Template</FieldLabel>
                          <RadioGroup
                            value={selectedTemplate?.id ?? ""}
                            onValueChange={(value) => {
                              const template = templates.find(
                                (t) => t.id === value,
                              );
                              setSelectedTemplate(template ?? null);
                              setValue("templateId", value);
                              trigger("templateId");
                            }}
                          >
                            {[...templates]
                              .sort((a, b) => b.id.localeCompare(a.id))
                              .map((template) => (
                                <label
                                  key={template.id}
                                  htmlFor={`template-${template.id}`}
                                  className="cursor-pointer"
                                >
                                  <Card
                                    className={`p-4 transition-colors hover:border-primary ${
                                      selectedTemplate?.id === template.id
                                        ? "border-primary bg-accent"
                                        : ""
                                    }`}
                                  >
                                    <div className="flex items-start gap-3">
                                      <RadioGroupItem
                                        value={template.id}
                                        id={`template-${template.id}`}
                                        className="mt-1"
                                      />
                                      <div className="flex-1 space-y-1">
                                        <h3 className="font-semibold text-base">
                                          {template.name}
                                        </h3>
                                        <p className="text-sm text-muted-foreground">
                                          {template.description}
                                        </p>
                                      </div>
                                    </div>
                                  </Card>
                                </label>
                              ))}
                          </RadioGroup>
                          <FieldError
                            errors={
                              errors.templateId
                                ? [errors.templateId]
                                : undefined
                            }
                          />
                        </Field>
                        <div className="flex justify-end gap-2 pt-4">
                          <Button
                            variant="secondary"
                            onClick={() => setOpen(false)}
                          >
                            Cancel
                          </Button>
                          <Button
                            onClick={async () => {
                              const isValid = await trigger([
                                "name",
                                "description",
                                "tags",
                                "templateId",
                              ]);
                              if (isValid) {
                                stepperRef.current?.nextStep();
                              }
                            }}
                          >
                            Next
                          </Button>
                        </div>
                      </div>
                    </InteractiveStepperContent>

                    <InteractiveStepperContent step={2} className="w-full">
                      <div className="space-y-4 w-full">
                        <Field>
                          <FieldLabel htmlFor="source-filename">
                            Source Filename
                          </FieldLabel>
                          <Select
                            value={watch("sourceFileName")}
                            onValueChange={(value) => {
                              setValue("sourceFileName", value);
                              trigger("sourceFileName");
                            }}
                          >
                            <SelectTrigger id="source-filename">
                              <SelectValue placeholder="Select source filename" />
                            </SelectTrigger>
                            <SelectContent>
                              {videoOptions.map((fn) => (
                                <SelectItem key={fn} value={fn}>
                                  {fn}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <FieldError
                            errors={
                              errors.sourceFileName
                                ? [errors.sourceFileName]
                                : undefined
                            }
                          />
                        </Field>

                        <Field>
                          <FieldLabel htmlFor="detection-model">
                            Detection Model
                          </FieldLabel>
                          <Select
                            value={watch("detectionModel")}
                            onValueChange={(value) => {
                              setValue("detectionModel", value);
                              trigger("detectionModel");
                            }}
                          >
                            <SelectTrigger id="detection-model">
                              <SelectValue placeholder="Select detection model" />
                            </SelectTrigger>
                            <SelectContent>
                              {models
                                ?.filter(
                                  (model) => model.category === "detection",
                                )
                                .map((model) => (
                                  <SelectItem
                                    key={model.display_name}
                                    value={model.display_name}
                                  >
                                    {model.display_name}
                                  </SelectItem>
                                ))}
                            </SelectContent>
                          </Select>
                          <FieldError
                            errors={
                              errors.detectionModel
                                ? [errors.detectionModel]
                                : undefined
                            }
                          />
                        </Field>

                        {selectedTemplate &&
                          selectedTemplate.id.toLowerCase() ===
                            "detect-classify" && (
                            <Field>
                              <FieldLabel htmlFor="classification-model">
                                Classification Model
                              </FieldLabel>
                              <Select
                                value={watch("classificationModel")}
                                onValueChange={(value) => {
                                  setValue("classificationModel", value);
                                  trigger("classificationModel");
                                }}
                              >
                                <SelectTrigger id="classification-model">
                                  <SelectValue placeholder="Select classification model" />
                                </SelectTrigger>
                                <SelectContent>
                                  {models
                                    ?.filter(
                                      (model) =>
                                        model.category === "classification",
                                    )
                                    .map((model) => (
                                      <SelectItem
                                        key={model.display_name}
                                        value={model.display_name}
                                      >
                                        {model.display_name}
                                      </SelectItem>
                                    ))}
                                </SelectContent>
                              </Select>
                              <FieldError
                                errors={
                                  errors.classificationModel
                                    ? [errors.classificationModel]
                                    : undefined
                                }
                              />
                            </Field>
                          )}

                        <div className="flex justify-end gap-2 pt-4">
                          <Button
                            variant="secondary"
                            onClick={() => stepperRef.current?.prevStep()}
                          >
                            Previous
                          </Button>
                          <Button
                            disabled={isCreating}
                            onClick={handleSubmit(onSubmitTemplate)}
                          >
                            {isCreating ? "Creating..." : "Create"}
                          </Button>
                        </div>
                      </div>
                    </InteractiveStepperContent>
                  </InteractiveStepper>
                </Field>
              </div>
            ) : (
              <div className="flex items-center justify-center h-96 border-2 border-dashed rounded-lg">
                <p className="text-muted-foreground">No templates available</p>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
};
