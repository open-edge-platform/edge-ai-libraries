import { useState } from "react";
import { Upload } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useToGraphMutation } from "@/api/api.generated";
import { toast } from "sonner";
import {
  type Edge as ReactFlowEdge,
  type Node as ReactFlowNode,
  type Viewport,
} from "@xyflow/react";
import { createGraphLayout } from "./utils/graphLayout";

interface ImportPipelineButtonProps {
  onImport: (
    nodes: ReactFlowNode[],
    edges: ReactFlowEdge[],
    viewport: Viewport,
    shouldFitView: boolean,
  ) => void;
}

const ImportPipelineButton = ({ onImport }: ImportPipelineButtonProps) => {
  const [open, setOpen] = useState(false);
  const [pipelineDescription, setPipelineDescription] = useState("");
  const [toGraph, { isLoading }] = useToGraphMutation();

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

  const handleConvertAndImport = async () => {
    if (!pipelineDescription.trim()) {
      toast.error("Pipeline description is empty");
      return;
    }

    try {
      const result = await toGraph({
        pipelineDescription: {
          pipeline_description: pipelineDescription,
        },
      }).unwrap();

      const nodesWithPositions = createGraphLayout(
        result.nodes.map((node) => ({
          id: node.id,
          type: node.type,
          data: node.data,
          position: { x: 0, y: 0 },
        })),
        result.edges,
      );

      const viewport: Viewport = {
        x: 0,
        y: 0,
        zoom: 1,
      };

      onImport(nodesWithPositions, result.edges, viewport, true);

      toast.success("Pipeline imported successfully");
      setOpen(false);
      setPipelineDescription("");
    } catch (error) {
      toast.error("Failed to import pipeline", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
      console.error("Failed to import pipeline:", error);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          className="bg-blue-600 hover:bg-blue-700 text-white p-2 rounded-lg shadow-lg transition-colors"
          title="Import Pipeline"
        >
          <Upload className="w-5 h-5" />
        </button>
      </DialogTrigger>
      <DialogContent className="!max-w-6xl">
        <DialogHeader>
          <DialogTitle>Import Pipeline</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
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
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-primary file:text-primary-foreground hover:file:bg-primary/90"
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
              className="w-full h-64 p-3 border rounded-md resize-none font-mono text-sm"
            />
          </div>

          <div className="flex justify-end gap-2">
            <button
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
              onClick={() => {
                setOpen(false);
                setPipelineDescription("");
              }}
            >
              Cancel
            </button>
            <button
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              onClick={handleConvertAndImport}
              disabled={isLoading || !pipelineDescription.trim()}
            >
              {isLoading ? "Importing..." : "Import"}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default ImportPipelineButton;
