import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const Queue2Node = () => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-teal-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-teal-700 dark:text-teal-300">
          Queue2
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-teal-100 dark:bg-teal-900 rounded">
          Buffer
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">
        Simple data queue
      </div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-teal-500!"
      style={{ left: getHandleLeftPosition("queue2") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-teal-500!"
      style={{ left: getHandleLeftPosition("queue2") }}
    />
  </div>
);

export default Queue2Node;
