import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const GVAMetaPublishNodeWidth = 265;

type GVAMetaPublishNodeProps = {
  data: {
    method?: string;
    "file-format"?: string;
    "file-path"?: string;
  };
};

const GVAMetaPublishNode = ({ data }: GVAMetaPublishNodeProps) => (
  <PipelineNodeCard
    title="GVAMetaPublish"
    nodeType="gvametapublish"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.metadataPublish}
    minWidthClass="min-w-[16.5625rem]"
    details={
      <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
        {data.method && <span>{data.method}</span>}

        {data.method && (data["file-format"] || data["file-path"]) && (
          <span className="text-node-separator">•</span>
        )}

        {data["file-format"] && <span>{data["file-format"]}</span>}

        {data["file-format"] && data["file-path"] && (
          <span className="text-node-separator">•</span>
        )}

        {data["file-path"] && <span>{data["file-path"]}</span>}
      </div>
    }
    icon={
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
      />
    }
  />
);

export default GVAMetaPublishNode;
