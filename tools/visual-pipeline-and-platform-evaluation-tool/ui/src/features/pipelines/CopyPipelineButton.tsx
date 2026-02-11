import React, { useState, useEffect } from "react";
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
  useToDescriptionMutation,
} from "@/api/api.generated.ts";
import { toast } from "sonner";
import type { Pipeline } from "@/api/api.generated.ts";
import { isApiError } from "@/lib/apiUtils.ts";

interface CopyPipelineButtonProps {
  pipelines: Record<string, Pipeline>;
  baseName: string;
  description: string;
  children: React.ReactNode;
}

export const CopyPipelineButton = ({
  pipelines,
  baseName,
  description: pipelineDescription,
  children,
}: CopyPipelineButtonProps) => {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const tags = Object.keys(pipelines);
  const [selectedTag, setSelectedTag] = useState(tags[0] ?? "");
  const selectedPipeline = pipelines[selectedTag];

  const [name, setName] = useState(`Copy of ${baseName} [${tags[0] ?? ""}]`);
  const [nameError, setNameError] = useState(false);
  const [description, setDescription] = useState(pipelineDescription);
  const [isNameManuallyEdited, setIsNameManuallyEdited] = useState(false);

  const [createPipeline, { isLoading: isCreating }] =
    useCreatePipelineMutation();
  const [toDescription, { isLoading: isConverting }] =
    useToDescriptionMutation();

  useEffect(() => {
    if (open) {
      setSelectedTag(tags[0] ?? "");
      setName(`Copy of ${baseName} [${tags[0] ?? ""}]`);
      setDescription(pipelineDescription);
      setIsNameManuallyEdited(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, baseName, pipelineDescription]);

  const handleCopy = async () => {
    if (!name.trim()) {
      toast.error("Name is required");
      return;
    }

    if (!selectedPipeline) {
      toast.error("No pipeline variant selected");
      return;
    }

    try {
      // Step 1: Convert pipeline graph to description
      const descriptionResponse = await toDescription({
        pipelineGraph: selectedPipeline.pipeline_graph,
      }).unwrap();

      // Step 2: Create new pipeline with the description
      const response = await createPipeline({
        pipelineDefinition: {
          name: name.trim(),
          description: description.trim(),
          source: "USER_CREATED",
          type: selectedPipeline.type,
          pipeline_description: descriptionResponse.pipeline_description,
          parameters: selectedPipeline.parameters,
        },
      }).unwrap();

      if (response.id) {
        setOpen(false);
        toast.success("Pipeline copied successfully");
        navigate(`/pipelines/${response.id}`);
      }
    } catch (error) {
      const errorMessage = isApiError(error)
        ? error.data.message
        : "Unknown error";

      if (errorMessage.startsWith("Invalid version")) {
        setNameError(true);
      } else {
        toast.error("Failed to copy pipeline", {
          description: errorMessage,
        });
      }

      console.error("Failed to copy pipeline:", error);
    }
  };

  const isLoading = isConverting || isCreating;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Copy Pipeline</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {tags.length > 1 && (
            <div>
              <label htmlFor="tag" className="block text-sm font-medium mb-2">
                Variant
              </label>
              <select
                id="tag"
                value={selectedTag}
                onChange={(e) => {
                  setSelectedTag(e.target.value);
                  if (!isNameManuallyEdited) {
                    setName(`Copy of ${baseName} [${e.target.value}]`);
                  }
                }}
                className="w-full px-3 py-2 border bg-background"
              >
                {tags.map((tag) => (
                  <option key={tag} value={tag}>
                    {tag}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label htmlFor="name" className="block text-sm font-medium mb-2">
              Name
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setIsNameManuallyEdited(true);
              }}
              placeholder="Enter pipeline name..."
              className="w-full px-3 py-2 border"
            />
            {nameError && (
              <span className="text-destructive">This name already exists</span>
            )}
          </div>

          <div>
            <label
              htmlFor="description"
              className="block text-sm font-medium mb-2"
            >
              Description
            </label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Enter pipeline description..."
              className="w-full h-24 px-3 py-2 border resize-none"
            />
          </div>

          <div className="flex justify-end gap-2">
            <button
              className="w-fit px-4 py-2 bg-background hover:bg-classic-blue dark:hover:bg-energy-blue border-2 border-classic-blue dark:border-energy-blue text-primary dark:text-energy-blue hover:text-white dark:hover:text-[#242528] transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
              onClick={() => setOpen(false)}
            >
              Cancel
            </button>
            <button
              className="w-fit px-4 py-2 bg-primary font-medium text-primary-foreground hover:bg-classic-blue-hover disabled:opacity-50 disabled:cursor-not-allowed dark:bg-energy-blue dark:hover:bg-energy-blue-tint-1 transition-colors"
              onClick={handleCopy}
              disabled={isLoading || !name.trim() || !selectedPipeline}
            >
              {isLoading ? "Copying..." : "Copy Pipeline"}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
