import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

const VideoXRawNode = () => (
  <PipelineNodeCard
    title="Video/x-raw"
    nodeType="video/x-raw(memory:VAMemory)"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.media}
    details={
      <div className="flex items-center gap-2 flex-wrap text-xs text-node-body-text">
        <span>VAMemory</span>
      </div>
    }
    icon={
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
      />
    }
  />
);

export default VideoXRawNode;
