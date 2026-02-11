import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";
import type { DeviceType } from "@/features/pipeline-editor/nodes/shared-types.ts";
import { usePipelineEditorContext } from "../PipelineEditorContext.ts";

export const GVAClassifyNodeWidth = 300;

type GVAClassifyNodeProps = {
  data: {
    model?: string;
    device?: DeviceType;
  };
};

const GVAClassifyNode = ({ data }: GVAClassifyNodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();

  return (
    <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-purple-400 min-w-[300px]">
      <div className="flex gap-3">
        <div className="flex-shrink-0 w-10 h-10 rounded bg-purple-100 dark:bg-purple-900 flex items-center justify-center self-center">
          <svg
            className="w-6 h-6 text-purple-600 dark:text-purple-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"
            />
          </svg>
        </div>

        <div className="flex-1 flex flex-col">
          <div className="text-xl font-bold text-purple-700 dark:text-purple-300">
            {simpleGraph ? "Image Classification" : "GVAClassify"}
          </div>

          <div className="flex items-center gap-1 flex-wrap text-xs text-gray-700 dark:text-gray-300">
            {data.device && <span>{data.device}</span>}

            {data.model && (
              <>
                {data.device && <span className="text-gray-400">•</span>}
                <span
                  className="truncate max-w-[185px]"
                  title={data.model.split("/").pop() ?? data.model}
                >
                  {data.model.split("/").pop() ?? data.model}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 bg-purple-500!"
        style={{ left: getHandleLeftPosition("gvaclassify") }}
      />

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-purple-500!"
        style={{ left: getHandleLeftPosition("gvaclassify") }}
      />
    </div>
  );
};

export default GVAClassifyNode;
