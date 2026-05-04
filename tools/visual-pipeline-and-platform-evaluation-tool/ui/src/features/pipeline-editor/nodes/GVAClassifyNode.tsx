import type { DeviceType } from "@/features/pipeline-editor/nodes/shared-types.ts";
import { usePipelineEditorContext } from "../PipelineEditorContext.ts";
import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

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
    <PipelineNodeCard
      title={simpleGraph ? "Image Classification" : "GVAClassify"}
      nodeType="gvaclassify"
      roleClasses={PIPELINE_NODE_ROLE_CLASSES.aiClassify}
      minWidthClass="min-w-[18.75rem]"
      details={
        <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
          {data.device && <span>{data.device}</span>}

          {data.model && (
            <>
              {data.device && <span className="text-node-separator">•</span>}
              <span
                className="truncate max-w-[11.5625rem]"
                title={data.model.split("/").pop() ?? data.model}
              >
                {data.model.split("/").pop() ?? data.model}
              </span>
            </>
          )}
        </div>
      }
      icon={
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"
        />
      }
    />
  );
};

export default GVAClassifyNode;
