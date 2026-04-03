import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

const QueueNode = () => (
  <PipelineNodeCard
    title="Queue"
    nodeType="queue"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.buffer}
    icon={
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M4 7h16M4 12h16M4 17h16"
      />
    }
  />
);

export default QueueNode;
