import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

const Queue2Node = () => (
  <PipelineNodeCard
    title="Queue2"
    nodeType="queue2"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.buffer}
    icon={
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M4 6h16M4 12h16M4 18h16"
      />
    }
  />
);

export default Queue2Node;
