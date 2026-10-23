import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

const VideoRateNode = () => (
  <PipelineNodeCard
    title="VideoRate"
    nodeType="videorate"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.transform}
    icon={
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M12 8v4l3 2m6-2a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    }
  />
);

export default VideoRateNode;
