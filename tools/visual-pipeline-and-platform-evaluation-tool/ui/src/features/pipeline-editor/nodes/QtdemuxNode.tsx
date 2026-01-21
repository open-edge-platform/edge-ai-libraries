import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const QtdemuxNode = () => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-green-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-green-700 dark:text-green-300">
          QtDemux
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-green-100 dark:bg-green-900 rounded">
          Demuxer
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">
        QuickTime demultiplexer
      </div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-green-500!"
      style={{ left: getHandleLeftPosition("qtdemux") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-green-500!"
      style={{ left: getHandleLeftPosition("qtdemux") }}
    />
  </div>
);

export default QtdemuxNode;
