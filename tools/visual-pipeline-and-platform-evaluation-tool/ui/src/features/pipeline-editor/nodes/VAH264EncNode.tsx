import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const VAH264EncNode = () => (
  <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-rose-400 min-w-40">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-rose-700">VAH264Enc</div>
        <div className="text-xs text-gray-500 px-2 py-1 bg-rose-100 rounded">
          Encoder
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600">VA-API H.264 encoder</div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-rose-500!"
      style={{ left: getHandleLeftPosition("vah264enc") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-rose-500!"
      style={{ left: getHandleLeftPosition("vah264enc") }}
    />
  </div>
);

export default VAH264EncNode;
