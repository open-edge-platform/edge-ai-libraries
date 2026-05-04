import { usePipelineEditorContext } from "../PipelineEditorContext.ts";
import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const GVADetectNodeWidth = 280;

type GVADetectNodeProps = {
  data: {
    model?: string;
    device?: string;
    "object-class": string;
  };
};

const GVADetectNode = ({ data }: GVADetectNodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();

  return (
    <PipelineNodeCard
      title={simpleGraph ? "Object Detection" : "GVADetect"}
      nodeType="gvadetect"
      roleClasses={PIPELINE_NODE_ROLE_CLASSES.aiDetect}
      minWidthClass="min-w-[17.5rem]"
      details={
        <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
          {data.device && <span>{data.device}</span>}

          {data.model && (
            <>
              {data.device && <span className="text-node-separator">•</span>}
              <span
                className="truncate max-w-[10.3125rem]"
                title={data.model.split("/").pop() || data.model}
              >
                {data.model.split("/").pop() || data.model}
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
        <>
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
          />
        </>
      }
    />
  );
};

export default GVADetectNode;
