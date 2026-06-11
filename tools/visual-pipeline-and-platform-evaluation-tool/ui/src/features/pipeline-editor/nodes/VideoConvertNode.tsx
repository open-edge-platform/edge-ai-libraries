import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const VideoConvertNodeWidth = 235;

const VideoConvertNode = () => (
  <PipelineNodeCard
    title="VideoConvert"
    nodeType="videoconvert"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.transform}
    minWidthClass="min-w-[14.6875rem]"
    icon={
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"
      />
    }
  />
);

export default VideoConvertNode;
