import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

const Mp4MuxNode = () => (
  <PipelineNodeCard
    title="Mp4Mux"
    nodeType="mp4mux"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.mux}
    icon={
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
      />
    }
  />
);

export default Mp4MuxNode;
