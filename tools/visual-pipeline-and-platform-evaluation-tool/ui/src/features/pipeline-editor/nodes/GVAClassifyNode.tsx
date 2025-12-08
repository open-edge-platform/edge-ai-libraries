import { Handle, Position } from "@xyflow/react";
import type { DeviceType } from "@/features/pipeline-editor/nodes/shared-types.ts";

type GVAClassifyNodeProps = {
  data: {
    model?: string;
    device?: DeviceType;
  };
};

const GVAClassifyNode = ({ data }: GVAClassifyNodeProps) => (
  <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-purple-400 min-w-40">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-purple-700">GVAClassify</div>
        <div className="text-xs text-gray-500 px-2 py-1 bg-purple-100 rounded">
          Classification
        </div>
      </div>

      {/* Model Property */}
      {data.model && (
        <div className="text-xs text-gray-600 mb-2">
          <span className="font-medium">Model:</span>
          <div className="mt-1 p-2 bg-purple-50 rounded text-xs font-mono">
            {data.model.split("/").pop() || data.model}
          </div>
        </div>
      )}

      {data.device && (
        <div className="text-xs text-gray-600 mb-2">
          <span className="font-medium">Device:</span>
          <div className="mt-1 p-2 bg-purple-50 rounded text-xs font-mono">
            {data.device}
          </div>
        </div>
      )}

      {/* Description */}
      <div className="text-xs text-gray-600">
        Intel DL Streamer classification
      </div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Left}
      className="w-3 h-3 bg-purple-500!"
      style={{ top: 40 }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Right}
      className="w-3 h-3 bg-purple-500!"
      style={{ top: 40 }}
    />
  </div>
);

export default GVAClassifyNode;
