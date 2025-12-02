import { Handle, Position } from "@xyflow/react";

export const FileSrcNodeWidth = 200;

type FileSrcNodeProps = {
  data: {
    location: string;
  };
};

const FileSrcNode = ({ data }: FileSrcNodeProps) => (
  <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-blue-400 min-w-[200px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-blue-700">FileSrc</div>
        <div className="text-xs text-gray-500 px-2 py-1 bg-blue-100 rounded">
          Source
        </div>
      </div>

      {/* Location Property */}
      <div className="text-xs text-gray-600">
        <span className="font-medium">Location:</span>
        <div className="mt-1 p-2 bg-gray-50 rounded text-xs font-mono break-all">
          {data.location.split("/").pop() || data.location}
        </div>
      </div>
    </div>

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Right}
      className="w-3 h-3 bg-blue-500!"
      style={{ top: 40 }}
    />
  </div>
);

export default FileSrcNode;
