import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "../shared";

export const SourceNodeWidth = 280;

type SourceNodeProps = {
  data: {
    kind?: string;
    source?: string;
  };
};

const SourceNode = ({ data }: SourceNodeProps) => {
  return (
    <PipelineNodeCard
      title="Input"
      nodeType="source"
      roleClasses={PIPELINE_NODE_ROLE_CLASSES.source}
      minWidthClass="min-w-[17.5rem]"
      handles="source"
      details={
        <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
          {data.kind && <span>{data.kind}</span>}

          {data.source && (
            <>
              {data.kind && <span className="text-node-separator">•</span>}
              <span className="truncate max-w-[8.5rem]" title={data.source}>
                {data.source}
              </span>
            </>
          )}
        </div>
      }
      icon={
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
        />
      }
    />
  );
};

export default SourceNode;
