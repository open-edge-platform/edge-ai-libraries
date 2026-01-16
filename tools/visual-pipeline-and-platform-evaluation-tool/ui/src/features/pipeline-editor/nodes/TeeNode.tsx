import { Handle, Position } from "@xyflow/react";

export const TeeNodeWidth = 180;

const TeeNode = () => (
  <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-sky-400 min-w-40">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-sky-700">Tee</div>
        <div className="text-xs text-gray-500 px-2 py-1 bg-sky-100 rounded">
          Splitter
        </div>
      </div>

      {/* Description */}
      <div className="text-xs text-gray-600">Stream splitting element</div>
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Left}
      className="w-3 h-3 bg-sky-500!"
      style={{ top: 40 }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Right}
      className="w-3 h-3 bg-sky-500!"
      style={{ top: 40 }}
    />
  </div>
);

export default TeeNode;
