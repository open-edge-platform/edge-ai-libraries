import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

const VaapiDecodebinNode = () => (
  <PipelineNodeCard
    title="VaapiDecodebin"
    nodeType="vaapidecodebin"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.decode}
    icon={
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z"
      />
    }
  />
);

export default VaapiDecodebinNode;
