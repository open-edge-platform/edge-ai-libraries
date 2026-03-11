import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../../utils/graphLayout";

export const SourceNodeWidth = 330;

type SourceNodeProps = {
  data: {
    kind?: string;
    source?: string;
  };
};

const SourceNode = ({ data }: SourceNodeProps) => {
  return (
    <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-blue-400 min-w-[330px]">
      <div className="flex gap-3">
        <div className="shrink-0 w-10 h-10 rounded bg-blue-100 dark:bg-blue-900 flex items-center justify-center self-center">
          <svg
            className="w-6 h-6 text-blue-600 dark:text-blue-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
            />
          </svg>
        </div>

        <div className="flex-1 flex flex-col">
          <div className="text-xl font-bold text-blue-700 dark:text-blue-300">
            Input
          </div>

          <div className="flex items-center gap-1 flex-wrap text-xs text-gray-700 dark:text-gray-300">
            {data.kind && <span>{data.kind}</span>}

            {data.source && (
              <>
                {data.kind && <span className="text-gray-400">•</span>}
                <span className="truncate max-w-[185px]" title={data.source}>
                  {data.source}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-blue-500!"
        style={{ left: getHandleLeftPosition("source") }}
      />
    </div>
  );
};

export default SourceNode;
