import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const VideoXRawNode = () => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-slate-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-slate-700 dark:text-slate-300">
          Video/x-raw
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-slate-100 dark:bg-slate-900 rounded">
          Caps
        </div>
      </div>

      {/* Memory Information */}
      <div className="text-xs text-gray-600 dark:text-gray-300 mb-2">
        <span className="font-medium">Memory:</span>
        <div className="mt-1 p-2 bg-gray-50 dark:bg-gray-800 rounded text-xs font-mono">
          VAMemory
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">
        Raw video capabilities
      </div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-slate-500!"
      style={{ left: getHandleLeftPosition("video/x-raw(memory:VAMemory)") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-slate-500!"
      style={{ left: getHandleLeftPosition("video/x-raw(memory:VAMemory)") }}
    />
  </div>
);

export default VideoXRawNode;
