import { Handle, Position } from "@xyflow/react";

const GVAWatermarkNode = () => (
  <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-pink-400 min-w-40">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-pink-700">GVAWatermark</div>
        <div className="text-xs text-gray-500 px-2 py-1 bg-pink-100 rounded">
          Overlay
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600">GStreamer VA watermark</div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Left}
      className="w-3 h-3 bg-pink-500!"
      style={{ top: 40 }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Right}
      className="w-3 h-3 bg-pink-500!"
      style={{ top: 40 }}
    />
  </div>
);

export default GVAWatermarkNode;
