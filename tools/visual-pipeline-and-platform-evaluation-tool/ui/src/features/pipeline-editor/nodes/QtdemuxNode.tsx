import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

const QtdemuxNode = () => (
  <PipelineNodeCard
    title="QtDemux"
    nodeType="qtdemux"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.demux}
    icon={
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"
      />
    }
  />
);

export default QtdemuxNode;
