import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const GVAFpsCounterNodeWidth = 255;

type GVAFpsCounterNodeProps = {
  data: {
    "starting-frame"?: number;
  };
};

const GVAFpsCounterNode = ({ data }: GVAFpsCounterNodeProps) => (
  <PipelineNodeCard
    title="GVAFpsCounter"
    nodeType="gvafpscounter"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.counter}
    minWidthClass="min-w-[15.9375rem]"
    details={
      <div className="flex items-center gap-2 flex-wrap text-xs text-node-body-text">
        {data["starting-frame"] !== undefined && (
          <span>Start at frame: {data["starting-frame"]}</span>
        )}
      </div>
    }
    icon={
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M12 6V4m0 2a6 6 0 016 6h2a8 8 0 10-16 0h2a6 6 0 016-6zm-3.343 5.757l-1.414 1.415M12 12l2.828 2.828"
      />
    }
  />
);

export default GVAFpsCounterNode;
