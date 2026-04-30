import { cn } from "@/lib/utils";
import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const GVAMetaConvertNodeWidth = 270;

type GVAMetaConvertNodeProps = {
  data: {
    qos?: boolean;
    "timestamp-utc"?: boolean;
    format?: string;
  };
};

const GVAMetaConvertNode = ({ data }: GVAMetaConvertNodeProps) => {
  const qos = data.qos ?? false;
  const timestampUtc = data["timestamp-utc"] ?? false;
  const format = data.format ?? "json";

  return (
    <PipelineNodeCard
      title="GVAMetaConvert"
      nodeType="gvametaconvert"
      roleClasses={PIPELINE_NODE_ROLE_CLASSES.metadata}
      minWidthClass="min-w-[16.875rem]"
      details={
        <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
          <span className={cn(!qos && "line-through")}>qos</span>
          <span className="text-node-separator">•</span>
          <span className={cn(!timestampUtc && "line-through")}>
            timestamp-utc
          </span>
          <span className="text-node-separator">•</span>
          <span>{format}</span>
        </div>
      }
      icon={
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
        />
      }
    />
  );
};

export default GVAMetaConvertNode;
