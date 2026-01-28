import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

const AvDecH264Node = () => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-indigo-400 min-w-[220px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-indigo-700 dark:text-indigo-300">
          AvDecH264
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-indigo-100 dark:bg-indigo-900 rounded">
          Decoder
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">
        libav H.264 decoder
      </div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-indigo-500!"
      style={{ left: getHandleLeftPosition("avdec_h264") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-indigo-500!"
      style={{ left: getHandleLeftPosition("avdec_h264") }}
    />
  </div>
);

export default AvDecH264Node;
