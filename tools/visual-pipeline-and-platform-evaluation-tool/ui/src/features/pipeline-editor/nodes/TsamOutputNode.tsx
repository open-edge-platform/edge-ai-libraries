import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const TsamOutputNodeWidth = 280;

type TsamOutputNodeProps = {
  data: {
    method?: string;
    endpoint?: string;
    topic?: string;
  };
};

const TsamOutputNode = ({ data }: TsamOutputNodeProps) => (
  <PipelineNodeCard
    title="TSAM Output"
    nodeType="tsam-output"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.metadata}
    minWidthClass="min-w-[17.5rem]"
    details={
      <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
        {data.method && <span>{data.method.toUpperCase()}</span>}
        {data.method && data.topic && (
          <span className="text-node-separator">•</span>
        )}
        {data.topic && <span>{data.topic}</span>}
      </div>
    }
    icon={
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
      />
    }
  />
);

export default TsamOutputNode;
