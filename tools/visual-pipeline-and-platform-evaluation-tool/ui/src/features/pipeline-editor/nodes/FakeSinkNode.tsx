import { Handle, Position } from "@xyflow/react";

const FakeSinkNode = () => (
  <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-gray-400 min-w-40">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-gray-700">FakeSink</div>
        <div className="text-xs text-gray-500 px-2 py-1 bg-gray-100 rounded">
          Sink
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600">GStreamer fake sink</div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Left}
      className="w-3 h-3 bg-gray-500!"
      style={{ top: 40 }}
    />
  </div>
);

export default FakeSinkNode;
