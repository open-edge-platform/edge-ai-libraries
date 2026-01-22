import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const FileSinkNode = () => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-gray-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-gray-700 dark:text-gray-300">
          FileSink
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-gray-100 dark:bg-gray-800 rounded">
          Sink
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">
        Write to file
      </div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-gray-500!"
      style={{ left: getHandleLeftPosition("filesink") }}
    />
  </div>
);

export default FileSinkNode;
