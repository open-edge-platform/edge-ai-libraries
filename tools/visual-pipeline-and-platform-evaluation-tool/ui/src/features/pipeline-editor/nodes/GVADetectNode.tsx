import { Handle, Position } from "@xyflow/react";

export const GVADetectNodeWidth = 280;

type GVADetectNodeProps = {
  data: {
    model?: string;
    device?: string;
    "object-class": string;
  };
};

const GVADetectNode = ({ data }: GVADetectNodeProps) => (
  <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-indigo-400 min-w-[250px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-indigo-700">GVADetect</div>
        <div className="text-xs text-gray-500 px-2 py-1 bg-indigo-100 rounded">
          Detection
        </div>
      </div>

      {/* Model Property */}
      {data.model && (
        <div className="text-xs text-gray-600 mb-2">
          <span className="font-medium">Model:</span>
          <div className="mt-1 p-2 bg-gray-50 rounded text-xs font-mono break-all">
            {data.model.split("/").pop() || data.model}
          </div>
        </div>
      )}

      {/* Device Property */}
      {data.device && (
        <div className="text-xs text-gray-600 mb-2">
          <span className="font-medium">Device:</span>
          <div className="mt-1 p-2 bg-gray-50 rounded text-xs">
            {data.device}
          </div>
        </div>
      )}

      {/* Object class Property */}
      {data["object-class"] && (
        <div className="text-xs text-gray-600 mb-2">
          <span className="font-medium">Pre-process Backend:</span>
          <div className="mt-1 p-2 bg-gray-50 rounded text-xs">
            {data["object-class"]}
          </div>
        </div>
      )}

      {/* Description */}
      <div className="text-xs text-gray-600">GStreamer VA detection</div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Left}
      className="w-3 h-3 bg-indigo-500!"
      style={{ top: 40 }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Right}
      className="w-3 h-3 bg-indigo-500!"
      style={{ top: 40 }}
    />
  </div>
);

export default GVADetectNode;
