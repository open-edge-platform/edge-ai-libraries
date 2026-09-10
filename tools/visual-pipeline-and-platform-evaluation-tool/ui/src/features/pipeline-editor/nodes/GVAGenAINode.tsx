import { usePipelineEditorContext } from "../PipelineEditorContext.ts";
import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const GVAGenAINodeWidth = 367;

type GVAGenAINodeProps = {
  data: {
    model?: string;
    device?: string;
    "frame-rate"?: string;
    "chunk-size"?: string;
    prompt?: string;
    "generation-config"?: string;
    metrics?: string;
  };
};

const GVAGenAINode = ({ data }: GVAGenAINodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();
  const modelValue = data.model ?? "";

  return (
    <PipelineNodeCard
      title={simpleGraph ? "Video Captioning VLM" : "GVAGenAI"}
      nodeType="gvagenai"
      roleClasses={PIPELINE_NODE_ROLE_CLASSES.aiTrack}
      minWidthClass="min-w-[22.9375rem]"
      details={
        <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
          {data.device && <span>{data.device}</span>}

          {modelValue && (
            <>
              {data.device && <span className="text-node-separator">•</span>}
              <span className="truncate max-w-[180px]" title={modelValue}>
                {modelValue.split("/").pop() || modelValue}
              </span>
            </>
          )}

          {data["frame-rate"] !== undefined && (
            <>
              {(data.device || modelValue) && (
                <span className="text-node-separator">•</span>
              )}
              <span>fps: {data["frame-rate"]}</span>
            </>
          )}

          {data["chunk-size"] !== undefined && (
            <>
              {(data.device ||
                modelValue ||
                data["frame-rate"] !== undefined) && (
                <span className="text-node-separator">•</span>
              )}
              <span>chunk: {data["chunk-size"]}</span>
            </>
          )}
        </div>
      }
      icon={
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9.75 3v2.25M14.25 3v2.25M9.75 18.75V21M3 9.75h2.25M3 14.25h2.25M18.75 9.75H21M18.75 14.25H21M7.5 7.5h9v9h-9z"
        />
      }
    />
  );
};

export default GVAGenAINode;
