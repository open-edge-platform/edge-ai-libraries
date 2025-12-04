import { Handle, Position } from "@xyflow/react";

const VAH264DecNode = () => (
  <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-orange-400 min-w-40">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-orange-700">VAH264Dec</div>
        <div className="text-xs text-gray-500 px-2 py-1 bg-orange-100 rounded">
          Decoder
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600">VA-API H.264 decoder</div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Left}
      className="w-3 h-3 bg-orange-500!"
      style={{ top: 40 }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Right}
      className="w-3 h-3 bg-orange-500!"
      style={{ top: 40 }}
    />
  </div>
);

export default VAH264DecNode;
