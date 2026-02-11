import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

export const GVAMetaConvertNodeWidth = 270;

type GVAMetaConvertNodeProps = {
  data: {
    qos?: boolean;
    "timestamp-utc"?: boolean;
    format?: string;
  };
};

const GVAMetaConvertNode = ({ data }: GVAMetaConvertNodeProps) => {
  const qos = data.qos ?? false;
  const timestampUtc = data["timestamp-utc"] ?? false;
  const format = data.format ?? "json";

  return (
    <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-cyan-400 min-w-[270px]">
      <div className="flex gap-3">
        <div className="shrink-0 w-10 h-10 rounded bg-cyan-100 dark:bg-cyan-900 flex items-center justify-center self-center">
          <svg
            className="w-6 h-6 text-cyan-600 dark:text-cyan-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </div>

        <div className="flex-1 flex flex-col">
          <div className="text-xl font-bold text-cyan-700 dark:text-cyan-300">
            GVAMetaConvert
          </div>

          <div className="flex items-center gap-1 flex-wrap text-xs text-gray-700 dark:text-gray-300">
            <span className={!qos ? "line-through" : ""}>qos</span>
            <span className="text-gray-400">•</span>
            <span className={!timestampUtc ? "line-through" : ""}>
              timestamp-utc
            </span>
            <span className="text-gray-400">•</span>
            <span>{format}</span>
          </div>
        </div>
      </div>

      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 bg-cyan-500!"
        style={{ left: getHandleLeftPosition("gvametaconvert") }}
      />

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-cyan-500!"
        style={{ left: getHandleLeftPosition("gvametaconvert") }}
      />
    </div>
  );
};

export default GVAMetaConvertNode;
