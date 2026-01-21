import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const Mp4MuxNode = () => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-violet-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-violet-700 dark:text-violet-300">
          Mp4Mux
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-violet-100 dark:bg-violet-900 rounded">
          Muxer
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">MP4 muxer</div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-violet-500!"
      style={{ left: getHandleLeftPosition("mp4mux") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-violet-500!"
      style={{ left: getHandleLeftPosition("mp4mux") }}
    />
  </div>
);

export default Mp4MuxNode;
