import { useRef, useState } from "react";
import { FileJson, Terminal, Upload } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover.tsx";
import { useToGraphMutation } from "@/api/api.generated";
import { toast } from "sonner";
import {
  type Edge as ReactFlowEdge,
  type Node as ReactFlowNode,
  type Viewport,
} from "@xyflow/react";
import { createGraphLayout } from "./utils/graphLayout";
import { handleApiError } from "@/lib/apiUtils";

interface ImportPipelineButtonProps {
  onImport: (
    nodes: ReactFlowNode[],
    edges: ReactFlowEdge[],
    viewport: Viewport,
    shouldFitView: boolean,
  ) => void;
}

const ImportPipelineButton = ({ onImport }: ImportPipelineButtonProps) => {
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [pipelineDescription, setPipelineDescription] = useState("");
  const [toGraph, { isLoading }] = useToGraphMutation();
  const jsonFileInputRef = useRef<HTMLInputElement>(null);
  const txtFileInputRef = useRef<HTMLInputElement>(null);

  const handleJsonImport = () => {
    setPopoverOpen(false);
    jsonFileInputRef.current?.click();
  };

  const handleDescriptionImport = () => {
    setPopoverOpen(false);
    setDialogOpen(true);
  };

  const handleJsonFileChange = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const fileExtension = file.name.split(".").pop()?.toLowerCase();

    if (fileExtension !== "json") {
      toast.error("Invalid file type", {
        description: "Please upload a .json file",
      });
      return;
    }

    const fileContent = await file.text();

    const parsedData = JSON.parse(fileContent);

    if (!parsedData.nodes || !parsedData.edges) {
      toast.error("Invalid JSON format", {
        description: "JSON file must contain 'nodes' and 'edges' properties",
      });
      return;
    }

    const viewport = parsedData.viewport ?? { x: 0, y: 0, zoom: 1 };
    onImport(parsedData.nodes, parsedData.edges, viewport, false);
    toast.success("Pipeline imported");

    if (jsonFileInputRef.current) {
      jsonFileInputRef.current.value = "";
    }
  };

  const handleTxtFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
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
        result.pipeline_graph.nodes.map((node) => ({
          id: node.id,
          type: node.type,
          data: node.data,
          position: { x: 0, y: 0 },
        })),
        result.pipeline_graph.edges,
      );

      const viewport: Viewport = {
        x: 0,
        y: 0,
        zoom: 1,
      };

      onImport(nodesWithPositions, result.pipeline_graph.edges, viewport, true);

      toast.success("Pipeline imported successfully");
      setDialogOpen(false);
      setPipelineDescription("");
    } catch (error) {
      handleApiError(error, "Failed to import pipeline");
      console.error("Failed to import pipeline:", error);
    }
  };

  return (
    <>
      <input
        ref={jsonFileInputRef}
        className="hidden"
        type="file"
        accept=".json"
        onChange={handleJsonFileChange}
      />

      <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
        <PopoverTrigger asChild>
          <button
            className="bg-background hover:bg-classic-blue dark:text-energy-blue font-medium dark:hover:text-[#242528] dark:border-energy-blue dark:hover:bg-energy-blue border-2 border-classic-blue text-primary hover:text-white px-3 py-2 transition-colors flex items-center gap-2"
            title="Import Pipeline"
          >
            <Upload className="w-5 h-5" />
            <span>Import</span>
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-64">
          <div className="space-y-2">
            <h3 className="font-semibold text-sm mb-2">Import Pipeline</h3>
            <button
              onClick={handleJsonImport}
              className="w-full text-left px-3 py-2 rounded hover:bg-gray-100 transition-colors text-sm flex items-start gap-2"
            >
              <FileJson className="w-4 h-4 mt-0.5 shrink-0" />
              <div>
                <div className="font-medium">Import JSON File</div>
                <div className="text-xs text-gray-500">
                  Import Pipeline Editor state
                </div>
              </div>
            </button>
            <button
              onClick={handleDescriptionImport}
              className="w-full text-left px-3 py-2 rounded hover:bg-gray-100 transition-colors text-sm flex items-start gap-2"
            >
              <Terminal className="w-4 h-4 mt-0.5 shrink-0" />
              <div>
                <div className="font-medium">Import GST Description</div>
                <div className="text-xs text-gray-500">
                  Import pipeline description
                </div>
              </div>
            </button>
          </div>
        </PopoverContent>
      </Popover>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="!max-w-6xl">
          <DialogHeader>
            <DialogTitle>Import Pipeline Description</DialogTitle>
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
                ref={txtFileInputRef}
                id="file-upload"
                type="file"
                accept=".txt"
                onChange={handleTxtFileUpload}
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
                  setDialogOpen(false);
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
    </>
  );
};

export default ImportPipelineButton;
