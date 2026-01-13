import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../../utils/graphLayout";

export const DetectionModelWidth = 250;

type DetectionModelProps = {
  data: {
    modelName?: string;
    confidence?: number;
  };
};

const DetectionModel = ({ data }: DetectionModelProps) => (
  <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-purple-400 min-w-[250px]">
    <div className="flex flex-col">
      {/* Node Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="text-lg font-bold text-purple-700">Detection Model</div>
        <div className="text-xs text-gray-500 px-2 py-1 bg-purple-100 rounded">
          AI Model
        </div>
      </div>

      {/* Model Name Property */}
      <div className="text-xs text-gray-600 mb-2">
        <span className="font-medium">Model:</span>
        <div className="mt-1 p-2 bg-gray-50 rounded text-xs font-mono break-all">
          {data.modelName ? (
            data.modelName.split("/").pop() || data.modelName
          ) : (
            <span className="text-gray-400 italic">No model selected</span>
          )}
        </div>
      </div>

      {/* Confidence Property */}
      {data.confidence !== undefined && (
        <div className="text-xs text-gray-600">
          <span className="font-medium">Confidence:</span>
          <div className="mt-1 p-2 bg-gray-50 rounded text-xs">
            {(data.confidence * 100).toFixed(0)}%
          </div>
        </div>
      )}
    </div>

    {/* Input Handle */}
    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-purple-500!"
      style={{ left: getHandleLeftPosition("detectionmodel") }}
    />

    {/* Output Handle */}
    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-purple-500!"
      style={{ left: getHandleLeftPosition("detectionmodel") }}
    />
  </div>
);

export default DetectionModel;
