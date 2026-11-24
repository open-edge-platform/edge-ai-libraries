import { Fragment } from "react";
import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const GVAMetaPublishNodeWidth = 265;

type GVAMetaPublishNodeProps = {
  data: {
    method?: string;
    "file-format"?: string;
    "file-path"?: string;
    address?: string;
    topic?: string;
  };
};

const GVAMetaPublishNode = ({ data }: GVAMetaPublishNodeProps) => {
  const details =
    data.method === "mqtt"
      ? [data.method, data.address, data.topic]
      : [data.method, data["file-format"], data["file-path"]];
  const shownDetails = details.filter(Boolean);

  return (
    <PipelineNodeCard
      title="GVAMetaPublish"
      nodeType="gvametapublish"
      roleClasses={PIPELINE_NODE_ROLE_CLASSES.metadataPublish}
      minWidthClass="min-w-[16.5625rem]"
      details={
        <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
          {shownDetails.map((detail, index) => (
            <Fragment key={detail}>
              {index > 0 && <span className="text-node-separator">•</span>}
              <span>{detail}</span>
            </Fragment>
          ))}
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
};

export default GVAMetaPublishNode;
