import { usePipelineEditorContext } from "../PipelineEditorContext.ts";
import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

const FakeSinkNode = () => {
  const { simpleGraph } = usePipelineEditorContext();

  return (
    <PipelineNodeCard
      title={simpleGraph ? "Output" : "FakeSink"}
      nodeType="fakesink"
      roleClasses={PIPELINE_NODE_ROLE_CLASSES.sink}
      handles="target"
      details={
        <div className="text-xs text-node-body-text">default</div>
      }
      icon={
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
        />
      }
    />
  );
};

export default FakeSinkNode;
