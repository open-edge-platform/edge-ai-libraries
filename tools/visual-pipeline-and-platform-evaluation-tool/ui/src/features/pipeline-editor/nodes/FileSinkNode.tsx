import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";

type FileSinkNodeProps = {
  data: {
    location?: string;
  };
};

const FileSinkNode = ({ data }: FileSinkNodeProps) => (
  <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-gray-400 min-w-[220px]">
    <div className="flex gap-3">
      <div className="shrink-0 w-10 h-10 rounded bg-gray-100 dark:bg-gray-800 flex items-center justify-center self-center">
        <svg
          className="w-6 h-6 text-gray-600 dark:text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"
          />
        </svg>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="text-xl font-bold text-gray-700 dark:text-gray-300">
          FileSink
        </div>

        <div className="flex items-center gap-1 flex-wrap text-xs text-gray-700 dark:text-gray-300">
          {data.location && (
            <span className="max-w-[150px] truncate" title={data.location}>
              {data.location}
            </span>
          )}
        </div>
      </div>
    </div>

    <Handle
      type="target"
      position={Position.Top}
      className="w-3 h-3 bg-gray-500!"
      style={{ left: getHandleLeftPosition("filesink") }}
    />
  </div>
);

export default FileSinkNode;
