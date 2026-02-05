import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

export const SplitMuxSinkNodeWidth = 255;

type SplitMuxSinkNodeProps = {
  data: {
    location?: string;
  };
};

const SplitMuxSinkNode = ({ data }: SplitMuxSinkNodeProps) => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-sky-400 min-w-[255px]">
    <div className="flex gap-3">
      <div className="shrink-0 w-10 h-10 rounded bg-sky-100 dark:bg-sky-900 flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-sky-600 dark:text-sky-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-sky-700 dark:text-sky-300">
          Splitmuxsink
        </div>

        <div className="flex items-center gap-1 flex-wrap text-xs text-gray-700 dark:text-gray-300">
          {data.location && (
            <span className="max-w-[165px] truncate" title={data.location}>
              {data.location}
            </span>
          )}
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-sky-500!"
      style={{ left: getHandleLeftPosition("splitmuxsink") }}
    />
  </div>
);

export default SplitMuxSinkNode;
