import { useState, useEffect } from "react";
import { Plus } from "lucide-react";
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
  useToGraphMutation,
  useValidatePipelineMutation,
  useGetValidationJobStatusQuery,
} from "@/api/api.generated.ts";
import { toast } from "sonner";
import { isApiError } from "@/lib/apiUtils.ts";

export const AddPipelineButton = () => {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [pipelineDescription, setPipelineDescription] = useState("");
  const [validationJobId, setValidationJobId] = useState<string | null>(null);
  const [validationStatus, setValidationStatus] = useState<string>("");
  const [pendingPipelineData, setPendingPipelineData] = useState<{
    name: string;
    description: string;
    pipelineDescription: string;
  } | null>(null);

  const [createPipeline, { isLoading: isCreating }] =
    useCreatePipelineMutation();
  const [toGraph, { isLoading: isConverting }] = useToGraphMutation();
  const [validatePipeline, { isLoading: isValidating }] =
    useValidatePipelineMutation();

  const { data: validationJobStatus } = useGetValidationJobStatusQuery(
    { jobId: validationJobId! },
    {
      skip: !validationJobId,
      pollingInterval: 1000,
    },
  );

  useEffect(() => {
    if (!validationJobStatus) return;

    if (validationJobStatus.id !== validationJobId) return;

    const handleCreatePipeline = async () => {
      if (!pendingPipelineData) return;

      try {
        const response = await createPipeline({
          pipelineDefinition: {
            name: pendingPipelineData.name.trim(),
            description: pendingPipelineData.description.trim(),
            source: "USER_CREATED",
            type: "GStreamer",
            pipeline_description: pendingPipelineData.pipelineDescription,
            parameters: {
              default: {
                additionalProp1: {},
              },
            },
          },
        }).unwrap();

        if (response.id) {
          setOpen(false);
          setName("");
          setDescription("");
          setPipelineDescription("");
          setValidationJobId(null);
          setValidationStatus("");
          setPendingPipelineData(null);
          toast.success("Pipeline created successfully");
          navigate(`/pipelines/${response.id}`);
        }
      } catch (error) {
        const errorMessage = isApiError(error)
          ? error.data.message
          : "Unknown error";
        toast.error("Failed to create pipeline", {
          description: errorMessage,
        });
        console.error("Failed to create pipeline:", error);
        setValidationJobId(null);
        setValidationStatus("");
        setPendingPipelineData(null);
      }
    };

    if (validationJobStatus?.state === "COMPLETED") {
      if (validationJobStatus.is_valid) {
        handleCreatePipeline();
      } else {
        const errors =
          validationJobStatus.error_message?.join(", ") || "Validation failed";
        toast.error("Pipeline validation failed", {
          description: errors,
        });
        setValidationJobId(null);
        setValidationStatus("");
        setPendingPipelineData(null);
      }
    } else if (
      validationJobStatus?.state === "ERROR" ||
      validationJobStatus?.state === "ABORTED"
    ) {
      const errors =
        validationJobStatus.error_message?.join(", ") || "Validation error";
      toast.error("Pipeline validation error", {
        description: errors,
      });
      setValidationJobId(null);
      setValidationStatus("");
      setPendingPipelineData(null);
    }
  }, [
    validationJobStatus,
    createPipeline,
    navigate,
    pendingPipelineData,
    validationJobId,
  ]);

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      setPipelineDescription(content);
    };
    reader.readAsText(file);
  };

  const handleAdd = async () => {
    if (!name.trim() || !description.trim() || !pipelineDescription.trim()) {
      toast.error("Name, description and pipeline description are required");
      return;
    }

    // Reset any previous validation state
    setValidationJobId(null);
    setValidationStatus("");
    setPendingPipelineData(null);

    try {
      // Step 1: Convert description to graph
      setValidationStatus("Converting pipeline description...");
      const graphResponse = await toGraph({
        pipelineDescription: {
          pipeline_description: pipelineDescription,
        },
      }).unwrap();

      // Step 2: Validate pipeline graph
      setValidationStatus("Validating pipeline...");
      const validationResponse = await validatePipeline({
        pipelineValidationInput: {
          type: "GStreamer",
          pipeline_graph: graphResponse.pipeline_graph,
        },
      }).unwrap();

      // If validation returns job_id, start polling
      if ("job_id" in validationResponse) {
        setValidationJobId(validationResponse.job_id);
        setValidationStatus("Waiting for validation...");
        // Store the pipeline data for later use when validation completes
        setPendingPipelineData({
          name: name.trim(),
          description: description.trim(),
          pipelineDescription: pipelineDescription,
        });
      } else {
        // Immediate validation response
        setValidationStatus("");
        setValidationJobId(null);
        setPendingPipelineData(null);
      }
    } catch (error) {
      const errorMessage = isApiError(error)
        ? error.data.message
        : "Unknown error";
      toast.error("Failed to process pipeline", {
        description: errorMessage,
      });
      setValidationStatus("");
      setValidationJobId(null);
      setPendingPipelineData(null);
    }
  };

  const isLoading =
    isConverting || isValidating || !!validationJobId || isCreating;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button className="w-full h-full min-h-[200px] border-2 border-dashed border-gray-300 dark:border-gray-700 hover:border-classic-blue dark:hover:border-energy-blue hover:bg-blue-50 dark:hover:bg-energy-blue/5 transition-all flex flex-col items-center justify-center gap-3 text-carbon-tint-1 dark:text-gray-400 hover:text-classic-blue  dark:hover:text-energy-blue">
          <Plus className="w-12 h-12" />
          <span className="text-lg font-medium">Add New Pipeline</span>
        </button>
      </DialogTrigger>
      <DialogContent className="!max-w-6xl">
        <DialogHeader>
          <DialogTitle>Add New Pipeline</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <label htmlFor="name" className="block text-sm font-medium mb-2">
              Name
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Enter pipeline name..."
              className="w-full px-3 py-2 border"
            />
          </div>

          <div>
            <label
              htmlFor="description"
              className="block text-sm font-medium mb-2"
            >
              Description
            </label>
            <input
              id="description"
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Enter pipeline description..."
              className="w-full px-3 py-2 border"
            />
          </div>

          <div>
            <label
              htmlFor="file-upload"
              className="block text-sm font-medium mb-2"
            >
              Upload file with Pipeline Description (.txt)
            </label>
            <input
              id="file-upload"
              type="file"
              accept=".txt"
              onChange={handleFileUpload}
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:border-0 file:text-sm file:font-semibold file:bg-primary file:text-primary-foreground hover:file:bg-primary/90"
            />
          </div>

          <div>
            <label
              htmlFor="pipeline-description"
              className="block text-sm font-medium mb-2"
            >
              Pipeline Description
            </label>
            <textarea
              id="pipeline-description"
              value={pipelineDescription}
              onChange={(e) => setPipelineDescription(e.target.value)}
              placeholder="Paste or upload your pipeline description here..."
              className="w-full h-64 p-3 border resize-none font-mono text-sm"
            />
          </div>

          <div className="flex justify-end gap-2">
            <button
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 transition-colors"
              onClick={() => {
                setOpen(false);
                setName("");
                setDescription("");
                setPipelineDescription("");
              }}
            >
              Cancel
            </button>
            <button
              className="px-4 py-2 text-sm font-medium text-white bg-classic-blue hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              onClick={handleAdd}
              disabled={
                isLoading ||
                !name.trim() ||
                !description.trim() ||
                !pipelineDescription.trim()
              }
            >
              {validationStatus
                ? validationStatus
                : isLoading
                  ? "Processing..."
                  : "Add"}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
