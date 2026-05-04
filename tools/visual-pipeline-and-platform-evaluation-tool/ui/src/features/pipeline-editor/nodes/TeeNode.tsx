import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

const TeeNode = () => (
  <PipelineNodeCard
    title="Tee"
    nodeType="tee"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.buffer}
    icon={
      <>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 4v7m0 0l-5 5m5-5l5 5"
        />
        <circle cx="12" cy="11" r="1.5" fill="currentColor" />
        <circle cx="7" cy="16" r="1.5" fill="currentColor" />
        <circle cx="17" cy="16" r="1.5" fill="currentColor" />
      </>
    }
  />
);

export default TeeNode;
