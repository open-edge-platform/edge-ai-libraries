import { Handle, Position } from "@xyflow/react";

const VideoXRawNode = () => (
  <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-slate-400 min-w-40">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-slate-700">Video/x-raw</div>
        <div className="text-xs text-gray-500 px-2 py-1 bg-slate-100 rounded">
          Caps
        </div>
      </div>

      {/* Memory Information */}
      <div className="text-xs text-gray-600 mb-2">
        <span className="font-medium">Memory:</span>
        <div className="mt-1 p-2 bg-gray-50 rounded text-xs font-mono">
          VAMemory
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600">Raw video capabilities</div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Left}
      className="w-3 h-3 bg-slate-500!"
      style={{ top: 40 }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Right}
      className="w-3 h-3 bg-slate-500!"
      style={{ top: 40 }}
    />
  </div>
);

export default VideoXRawNode;
