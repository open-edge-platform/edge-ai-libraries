import { usePipelineEditorContext } from "../PipelineEditorContext.ts";
import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const GVAProximityTriggerPyNodeWidth = 330;

type GVAProximityTriggerPyNodeProps = {
  data: {
    "class-a"?: string;
    "class-b"?: string;
    distance?: number | string;
    frames?: number | string;
  };
};

const GVAProximityTriggerPyNode = ({ data }: GVAProximityTriggerPyNodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();

  return (
    <PipelineNodeCard
      title={simpleGraph ? "Proximity Trigger" : "GVAProximityTriggerPy"}
      nodeType="gvaproximitytrigger_py"
      roleClasses={PIPELINE_NODE_ROLE_CLASSES.aiMotionDetect}
      minWidthClass="min-w-[20.5rem]"
      details={
        <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
          {data["class-a"] && <span>A: {data["class-a"]}</span>}

          {data["class-b"] && (
            <>
              {data["class-a"] && <span className="text-node-separator">•</span>}
              <span>B: {data["class-b"]}</span>
            </>
          )}

          {data.distance !== undefined && (
            <>
              {(data["class-a"] || data["class-b"]) && (
                <span className="text-node-separator">•</span>
              )}
              <span>dist: {data.distance}px</span>
            </>
          )}

          {data.frames !== undefined && (
            <>
              {(data["class-a"] || data["class-b"] || data.distance !== undefined) && (
                <span className="text-node-separator">•</span>
              )}
              <span>frames: {data.frames}</span>
            </>
          )}
        </div>
      }
      icon={
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4.5 12h5m5 0h5m-15 0a3 3 0 113 3m12-3a3 3 0 10-3 3M9.5 12a2.5 2.5 0 115 0 2.5 2.5 0 01-5 0z"
        />
      }
    />
  );
};

export default GVAProximityTriggerPyNode;
