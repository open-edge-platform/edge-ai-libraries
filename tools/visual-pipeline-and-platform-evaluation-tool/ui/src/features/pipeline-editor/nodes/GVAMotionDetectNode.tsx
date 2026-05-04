import { usePipelineEditorContext } from "../PipelineEditorContext.ts";
import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const GVAMotionDetectNodeWidth = 280;

type GVAMotionDetectNodeProps = {
  data: {
    name?: string;
    "motion-threshold"?: number;
    "block-size"?: number;
  };
};

const GVAMotionDetectNode = ({ data }: GVAMotionDetectNodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();

  return (
    <PipelineNodeCard
      title={simpleGraph ? "Motion Detection" : "GVAMotionDetect"}
      nodeType="gvamotiondetect"
      roleClasses={PIPELINE_NODE_ROLE_CLASSES.aiMotionDetect}
      minWidthClass="min-w-[17.5rem]"
      details={
        <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
          {data.name && <span>{data.name}</span>}

          {data["motion-threshold"] !== undefined && (
            <>
              {data.name && <span className="text-node-separator">•</span>}
              <span>threshold: {data["motion-threshold"]}</span>
            </>
          )}

          {data["block-size"] !== undefined && (
            <>
              {(data.name || data["motion-threshold"] !== undefined) && (
                <span className="text-node-separator">•</span>
              )}
              <span>block: {data["block-size"]}</span>
            </>
          )}
        </div>
      }
      icon={
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M13 10V3L4 14h7v7l9-11h-7z"
        />
      }
    />
  );
};

export default GVAMotionDetectNode;
