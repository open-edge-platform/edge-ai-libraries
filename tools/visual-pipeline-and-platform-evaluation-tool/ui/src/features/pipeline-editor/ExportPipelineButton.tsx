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
import { toast } from "sonner";

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
        <button
          className="bg-background hover:bg-classic-blue dark:text-energy-blue font-medium dark:hover:text-[#242528] dark:border-energy-blue dark:hover:bg-energy-blue border-2 border-classic-blue text-primary hover:text-white px-3 py-2 transition-colors flex items-center gap-2"
          title="Export Pipeline"
        >
          <Download className="w-5 h-5" />
          <span>Export</span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64">
        <div className="space-y-2">
          <h3 className="font-semibold text-sm mb-2">Export Pipeline</h3>
          <button
            onClick={handleDownloadJson}
            className="w-full text-left px-3 py-2 rounded hover:bg-gray-100 transition-colors text-sm flex items-start gap-2"
          >
            <FileJson className="w-4 h-4 mt-0.5 shrink-0" />
            <div>
              <div className="font-medium">Download JSON File</div>
              <div className="text-xs text-gray-500">
                Export Pipeline Editor state
              </div>
            </div>
          </button>
          <button
            onClick={handleDownloadDescription}
            disabled={isLoading}
            className="w-full text-left px-3 py-2 rounded hover:bg-gray-100 transition-colors text-sm disabled:opacity-50 flex items-start gap-2"
          >
            <Terminal className="w-4 h-4 mt-0.5 shrink-0" />
            <div>
              <div className="font-medium">
                {isLoading ? "Generating..." : "Download GST Description"}
              </div>
              <div className="text-xs text-gray-500">
                Export pipeline description
              </div>
            </div>
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
};

export default ExportPipelineButton;
