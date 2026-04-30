import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

const VAH264DecNode = () => (
  <PipelineNodeCard
    title="VAH264Dec"
    nodeType="vah264dec"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.decode}
    icon={
      <>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
        />
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </>
    }
  />
);

export default VAH264DecNode;
