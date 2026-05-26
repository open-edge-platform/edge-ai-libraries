import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "./shared";

export const TsamUdfNodeWidth = 320;

type TsamUdfNodeProps = {
  data: {
    "udf-name"?: string;
    "udf-model"?: string;
    device?: string;
  };
};

const TsamUdfNode = ({ data }: TsamUdfNodeProps) => (
  <PipelineNodeCard
    title="Anomaly Detection UDF"
    nodeType="tsam-udf"
    roleClasses={PIPELINE_NODE_ROLE_CLASSES.aiDetect}
    minWidthClass="min-w-[20rem]"
    details={
      <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
        {data.device && <span>{data.device.toUpperCase()}</span>}
        {data.device && data["udf-name"] && (
          <span className="text-node-separator">•</span>
        )}
        {data["udf-name"] && (
          <span className="truncate max-w-[12rem]" title={data["udf-name"]}>
            {data["udf-name"]}
          </span>
        )}
      </div>
    }
    icon={
      <>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2z"
        />
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M15 13v6a2 2 0 002 2h2a2 2 0 002-2v-6a2 2 0 00-2-2h-2a2 2 0 00-2 2z"
        />
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M5 3l7 4 7-4M12 7v5"
        />
      </>
    }
  />
);

export default TsamUdfNode;
