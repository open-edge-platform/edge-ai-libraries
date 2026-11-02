import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const TsamIngestionNodeWidth = 300;

type TsamIngestionNodeProps = {
  data: {
    host?: string;
    port?: string;
  };
};

const TsamIngestionNode = ({ data }: TsamIngestionNodeProps) => (
  <PipelineNodeCard
    title="TSAM Ingestion"
    nodeType="tsam-ingestion"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.buffer}
    minWidthClass="min-w-[18.75rem]"
    details={
      <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
        {data.host && (
          <span className="truncate max-w-[12rem]" title={data.host}>
            {data.host}
          </span>
        )}
        {data.host && data.port && (
          <span className="text-node-separator">•</span>
        )}
        {data.port && <span>:{data.port}</span>}
      </div>
    }
    icon={
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4"
      />
    }
  />
);

export default TsamIngestionNode;
