import { Handle, Position } from "@xyflow/react";
import { getHandleLeftPosition } from "../utils/graphLayout";
import { usePipelineEditorContext } from "../PipelineEditorContext.ts";

const FakeSinkNode = () => {
  const { simpleGraph } = usePipelineEditorContext();

  return (
    <div className="p-4 rounded shadow-md bg-background border border-l-4 border-l-node-role-sink-border min-w-[13.75rem]">
      <div className="flex gap-3">
        <div className="shrink-0 w-10 h-10 rounded bg-node-role-sink-surface flex items-center justify-center self-center">
          <svg
            className="w-6 h-6 text-node-role-sink-icon"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
            />
          </svg>
        </div>

        <div className="flex-1 flex flex-col">
          <div className="text-xl font-bold text-node-role-sink-title">
            {simpleGraph ? "Output" : "FakeSink"}
          </div>
        </div>
      </div>

      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 bg-node-role-sink-handle!"
        style={{ left: getHandleLeftPosition("fakesink") }}
      />
    </div>
  );
};

export default FakeSinkNode;
