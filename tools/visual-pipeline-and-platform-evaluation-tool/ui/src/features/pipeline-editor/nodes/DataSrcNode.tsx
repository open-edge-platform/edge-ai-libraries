import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const DataSrcNodeWidth = 280;

type DataSrcNodeProps = {
  data: {
    location?: string;
    topic?: string;
  };
};

const DataSrcNode = ({ data }: DataSrcNodeProps) => (
  <PipelineNodeCard
    title="Input"
    nodeType="datasrc"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.source}
    minWidthClass="min-w-[17.5rem]"
    handles="source"
    details={
      <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
        {data.topic && <span>{data.topic}</span>}
        {data.topic && data.location && (
          <span className="text-node-separator">•</span>
        )}
        {data.location && (
          <span className="truncate max-w-[10.625rem]" title={data.location}>
            {data.location.split("/").pop() || data.location}
          </span>
        )}
      </div>
    }
    icon={
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4"
      />
    }
  />
);

export default DataSrcNode;
