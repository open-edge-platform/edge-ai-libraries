import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

const H264ParseNode = () => (
  <PipelineNodeCard
    title="H264Parse"
    nodeType="h264parse"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.parse}
    icon={
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
      />
    }
  />
);

export default H264ParseNode;
