import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const TeeNode = () => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-sky-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-sky-700 dark:text-sky-300">
          Tee
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-sky-100 dark:bg-sky-900 rounded">
          Splitter
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">
        Stream splitting element
      </div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-sky-500!"
      style={{ left: getHandleLeftPosition("tee") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-sky-500!"
      style={{ left: getHandleLeftPosition("tee") }}
    />
  </div>
);

export default TeeNode;
