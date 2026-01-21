import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const H264ParseNode = () => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-purple-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-purple-700 dark:text-purple-300">
          H264Parse
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-purple-100 dark:bg-purple-900 rounded">
          Parser
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">
        H.264 stream parser
      </div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-purple-500!"
      style={{ left: getHandleLeftPosition("h264parse") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-purple-500!"
      style={{ left: getHandleLeftPosition("h264parse") }}
    />
  </div>
);

export default H264ParseNode;
