import { useToDescriptionMutation } from "@/api/api.generated";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover.tsx";
import { handleApiError } from "@/lib/apiUtils";
import { downloadFile, MimeType } from "@/lib/fileUtils";
import type { Edge, Node, Viewport } from "@xyflow/react";
import { Download, FileJson, Terminal } from "lucide-react";
import { useState } from "react";
import { toast } from "@/lib/toast";
import { PipelineMenuOptionButton, PipelineToolbarButton } from "./shared";

type DownloadPipelineButtonProps = {
  nodes: Node[];
  edges: Edge[];
  viewport?: Viewport;
  pipelineName: string;
};

const ExportPipelineButton = ({
  nodes,
  edges,
  viewport,
  pipelineName,
}: DownloadPipelineButtonProps) => {
  const [open, setOpen] = useState(false);
  const [toDescription, { isLoading }] = useToDescriptionMutation();

  const handleDownloadJson = () => {
    const stateData = {
      nodes,
      edges,
      viewport,
    };
    const jsonString = JSON.stringify(stateData, null, 2);
    const filename = `${pipelineName}.json`;
    downloadFile(jsonString, filename, MimeType.JSON);
    toast.success("Pipeline state downloaded");
    setOpen(false);
  };

  const handleDownloadDescription = async () => {
    try {
      const apiNodes = nodes.map((node) => ({
        id: node.id,
        type: node.type ?? "default",
        data: Object.fromEntries(
          Object.entries(node.data ?? {}).map(([key, value]) => [
            key,
            typeof value === "object" && value !== null
              ? JSON.stringify(value)
              : String(value),
          ]),
        ),
      }));

      const response = await toDescription({
        pipelineGraph: {
          nodes: apiNodes,
          edges: edges,
        },
      }).unwrap();

      const description = response.pipeline_description;

      const filename = `${pipelineName}.txt`;
      downloadFile(description, filename);
      toast.success("Pipeline description downloaded");
      setOpen(false);
    } catch (error) {
      handleApiError(error, "Failed to generate pipeline description");
      console.error("Failed to generate description:", error);
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <PipelineToolbarButton
          title="Export Pipeline"
          icon={<Download className="w-5 h-5" />}
          label={<span>Export</span>}
          variant="accent-outline"
        />
      </PopoverTrigger>
      <PopoverContent className="w-64">
        <div className="space-y-2">
          <h3 className="font-semibold text-sm mb-2">Export Pipeline</h3>
          <PipelineMenuOptionButton
            onClick={handleDownloadJson}
            icon={<FileJson className="w-4 h-4 mt-0.5 shrink-0" />}
            title="Download JSON File"
            description="Export Pipeline Editor state"
          />
          <PipelineMenuOptionButton
            onClick={handleDownloadDescription}
            disabled={isLoading}
            icon={<Terminal className="w-4 h-4 mt-0.5 shrink-0" />}
            title={isLoading ? "Generating..." : "Download GST Description"}
            description="Export pipeline description"
          />
        </div>
      </PopoverContent>
    </Popover>
  );
};

export default ExportPipelineButton;
