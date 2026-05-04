import type { GVA_TRACKING_TYPES } from "@/features/pipeline-editor/nodes/GVATrackNode.config.ts";
import { usePipelineEditorContext } from "../PipelineEditorContext.ts";
import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export type GvaTrackingType = (typeof GVA_TRACKING_TYPES)[number];

type GVATrackNodeProps = {
  data: {
    "tracking-type": GvaTrackingType;
  };
};

const GVATrackNode = ({ data }: GVATrackNodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();

  return (
    <PipelineNodeCard
      title={simpleGraph ? "Tracking" : "GVATrack"}
      nodeType="gvatrack"
      roleClasses={PIPELINE_NODE_ROLE_CLASSES.aiTrack}
      details={
        <div className="flex items-center gap-2 flex-wrap text-xs text-node-body-text">
          {data["tracking-type"] && <span>{data["tracking-type"]}</span>}
        </div>
      }
      icon={
        <>
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
          />
        </>
      }
    />
  );
};

export default GVATrackNode;
