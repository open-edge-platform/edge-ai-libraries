import { Handle, Position } from "@xyflow/react";

export const GVAMetaConvertNodeWidth = 270;

const GVAMetaConvertNode = () => (
  <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-cyan-400 min-w-[270px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-cyan-700">GVAMetaConvert</div>
        <div className="text-xs text-gray-500 px-2 py-1 bg-cyan-100 rounded">
          Converter
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600">GStreamer VA meta converter</div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Left}
      className="w-3 h-3 bg-cyan-500!"
      style={{ top: 40 }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Right}
      className="w-3 h-3 bg-cyan-500!"
      style={{ top: 40 }}
    />
  </div>
);

export default GVAMetaConvertNode;
