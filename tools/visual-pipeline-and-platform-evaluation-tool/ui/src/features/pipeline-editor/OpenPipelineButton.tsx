import type { Edge, Node, Viewport } from "@xyflow/react";
import { FolderOpen } from "lucide-react";
import React, { useRef } from "react";
import { toast } from "sonner";

type OpenPipelineButtonProps = {
  onImport: (
    nodes: Node[],
    edges: Edge[],
    viewport: Viewport,
    shouldFitView: boolean,
  ) => void;
};

const OpenPipelineButton = ({ onImport }: OpenPipelineButtonProps) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (
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

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <>
      <input
        ref={fileInputRef}
        className="hidden"
        type="file"
        accept=".json"
        onChange={handleFileChange}
      />
      <button
        onClick={handleClick}
        className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-2 rounded-lg shadow-lg transition-colors disabled:opacity-50 flex items-center gap-2"
        title="Open Pipeline"
      >
        <FolderOpen className="w-5 h-5" />
        <span>Open</span>
      </button>
    </>
  );
};

export default OpenPipelineButton;
