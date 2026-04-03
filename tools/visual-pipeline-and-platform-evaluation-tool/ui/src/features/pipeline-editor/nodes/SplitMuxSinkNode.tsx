import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const SplitMuxSinkNodeWidth = 255;

type SplitMuxSinkNodeProps = {
  data: {
    location?: string;
  };
};

const SplitMuxSinkNode = ({ data }: SplitMuxSinkNodeProps) => (
  <PipelineNodeCard
    title="Splitmuxsink"
    nodeType="splitmuxsink"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.sink}
    minWidthClass="min-w-[15.9375rem]"
    handles="target"
    details={
      <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
        {data.location && (
          <span className="max-w-[10.3125rem] truncate" title={data.location}>
            {data.location}
          </span>
        )}
      </div>
    }
    icon={
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
      />
    }
  />
);

export default SplitMuxSinkNode;
