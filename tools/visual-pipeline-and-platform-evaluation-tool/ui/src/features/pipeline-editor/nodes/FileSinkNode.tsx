import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

type FileSinkNodeProps = {
  data: {
    location?: string;
  };
};

const FileSinkNode = ({ data }: FileSinkNodeProps) => (
  <PipelineNodeCard
    title="FileSink"
    nodeType="filesink"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.sink}
    handles="target"
    details={
      <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
        {data.location && (
          <span className="max-w-[9.375rem] truncate" title={data.location}>
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
        d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"
      />
    }
  />
);

export default FileSinkNode;
