import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

export const GVAMetaConvertNodeWidth = 273;

const GVAMetaConvertNode = () => (
  <div className="px-4 py-2 shadow-md bg-background border-2 border-cyan-400 min-w-[270px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-cyan-700 dark:text-cyan-300">
          GVAMetaConvert
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1 bg-cyan-100 dark:bg-cyan-900 rounded">
          Converter
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600 dark:text-gray-300">
        GStreamer VA meta converter
      </div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-cyan-500!"
      style={{ left: getHandleLeftPosition("gvametaconvert") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-cyan-500!"
      style={{ left: getHandleLeftPosition("gvametaconvert") }}
    />
  </div>
);

export default GVAMetaConvertNode;
