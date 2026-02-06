import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

export const GVAMetaPublishNodeWidth = 265;

type GVAMetaPublishNodeProps = {
  data: {
    method?: string;
    "file-format"?: string;
    "file-path"?: string;
  };
};

const GVAMetaPublishNode = ({ data }: GVAMetaPublishNodeProps) => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-emerald-400 min-w-[265px]">
    <div className="flex gap-3">
      <div className="shrink-0 w-10 h-10 rounded bg-emerald-100 dark:bg-emerald-900 flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-emerald-600 dark:text-emerald-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-emerald-700 dark:text-emerald-300">
          GVAMetaPublish
        </div>

        <div className="flex items-center gap-1 flex-wrap text-xs text-gray-700 dark:text-gray-300">
          {data.method && <span>{data.method}</span>}

          {data.method && (data["file-format"] || data["file-path"]) && (
            <span className="text-gray-400">•</span>
          )}

          {data["file-format"] && <span>{data["file-format"]}</span>}

          {data["file-format"] && data["file-path"] && (
            <span className="text-gray-400">•</span>
          )}

          {data["file-path"] && <span>{data["file-path"]}</span>}
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-emerald-500!"
      style={{ left: getHandleLeftPosition("gvametapublish") }}
    />

    <Handle
      type="source"
      position={Position.Bottom}
      className="w-3 h-3 bg-emerald-500!"
      style={{ left: getHandleLeftPosition("gvametapublish") }}
    />
  </div>
);

export default GVAMetaPublishNode;
