// SPDX-License-Identifier: Apache-2.0
import { usePipelineEditorContext } from "../../PipelineEditorContext.ts";
import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "../shared";

export const ProximityTriggerNodeWidth = 260;

type ProximityTriggerNodeProps = {
  data: {
    name?: string;
    "class-a"?: string;
    "class-b"?: string;
    distance?: number;
    frames?: number;
  };
};

const ProximityTriggerNode = ({ data }: ProximityTriggerNodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();
  const classA = data["class-a"];
  const classB = data["class-b"];

  return (
    <PipelineNodeCard
      title={simpleGraph ? "Proximity Trigger" : "gvaproximitytrigger_py"}
      nodeType="gvaproximitytrigger_py"
      roleClasses={PIPELINE_NODE_ROLE_CLASSES.transform}
      minWidthClass="min-w-[16.25rem]"
      details={
        <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
          {data.name && <span>{data.name}</span>}

          {(classA || classB) && (
            <>
              {data.name && <span className="text-node-separator">•</span>}
              <span>
                {classA ?? "?"} ↔ {classB ?? "?"}
              </span>
            </>
          )}

          {data.distance !== undefined && (
            <>
              {(data.name || classA || classB) && (
                <span className="text-node-separator">•</span>
              )}
              <span>distance: {data.distance}</span>
            </>
          )}

          {data.frames !== undefined && (
            <>
              {(data.name ||
                classA ||
                classB ||
                data.distance !== undefined) && (
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
          d="M13 10V3L4 14h7v7l9-11h-7z"
        />
      }
    />
  );
};

export default ProximityTriggerNode;
