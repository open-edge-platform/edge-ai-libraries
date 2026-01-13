import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../../utils/graphLayout";

export const VideoFileInputWidth = 220;

type VideoFileInputProps = {
  data: {
    filePath?: string;
  };
};

const VideoFileInput = ({ data }: VideoFileInputProps) => (
  <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-green-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-green-700">Video File Input</div>
        <div className="text-xs text-gray-500 px-2 py-1 bg-green-100 rounded">
          Input
        </div>
      </div>

      {/* File Path Property */}
      <div className="text-xs text-gray-600">
        <span className="font-medium">File:</span>
        <div className="mt-1 p-2 bg-gray-50 rounded text-xs font-mono break-all">
          {data.filePath ? (
            data.filePath.split("/").pop() || data.filePath
          ) : (
            <span className="text-gray-400 italic">No file selected</span>
          )}
        </div>
      </div>
    </div>

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-green-500!"
      style={{ left: getHandleLeftPosition("videofileinput") }}
    />
  </div>
);

export default VideoFileInput;
