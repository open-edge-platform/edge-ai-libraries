import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

export const QueueNodeWidth = 180;

const QueueNode = () => (
  <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-sky-400 min-w-40">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-sky-700">Queue</div>
        <div className="text-xs text-gray-500 px-2 py-1 bg-sky-100 rounded">
          Buffer
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600">Data buffering element</div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-sky-500!"
      style={{ left: getHandleLeftPosition("queue") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-sky-500!"
      style={{ left: getHandleLeftPosition("queue") }}
    />
  </div>
);

export default QueueNode;
