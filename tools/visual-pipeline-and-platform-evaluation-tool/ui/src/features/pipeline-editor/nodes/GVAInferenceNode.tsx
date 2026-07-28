// SPDX-License-Identifier: Apache-2.0
import type { DeviceType } from "@/features/pipeline-editor/nodes/shared-types.ts";
import { usePipelineEditorContext } from "../PipelineEditorContext.ts";
import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const GVAInferenceNodeWidth = 300;

type GVAInferenceNodeProps = {
  data: {
    model?: string;
    device?: DeviceType;
    "object-class"?: string;
  };
};

const GVAInferenceNode = ({ data }: GVAInferenceNodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();

  return (
    <PipelineNodeCard
      title={simpleGraph ? "Inference" : "GVAInference"}
      nodeType="gvainference"
      roleClasses={PIPELINE_NODE_ROLE_CLASSES.aiClassify}
      minWidthClass="min-w-[18.75rem]"
      details={
        <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
          {data.device && <span>{data.device}</span>}

          {data.model && (
            <>
              {data.device && <span className="text-node-separator">•</span>}
              <span
                className="truncate max-w-[10.75rem]"
                title={data.model.split("/").pop() ?? data.model}
              >
                {data.model.split("/").pop() ?? data.model}
              </span>
            </>
          )}

          {data["object-class"] && (
            <>
              {(data.model || data.device) && (
                <span className="text-node-separator">•</span>
              )}
              <span>{data["object-class"]}</span>
            </>
          )}
        </div>
      }
      icon={
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2v-4M9 21H5a2 2 0 01-2-2v-4m0 0h18"
        />
      }
    />
  );
};

export default GVAInferenceNode;
