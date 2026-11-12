// SPDX-License-Identifier: Apache-2.0
import { usePipelineEditorContext } from "../../PipelineEditorContext.ts";
import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "../shared";

export const SscapePostInferenceDataPublishNodeWidth = 290;

type SscapePostInferenceDataPublishNodeProps = {
  data: {
    name?: string;
    cameraid?: string;
    metadatagenpolicy?: string;
    "mqtt-host"?: string;
    "mqtt-port"?: number | string;
    "publish-image"?: boolean | string;
  };
};

const SscapePostInferenceDataPublishNode = ({
  data,
}: SscapePostInferenceDataPublishNodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();
  const publishImage = String(data["publish-image"]) === "true";
  const broker = data["mqtt-host"]
    ? `${data["mqtt-host"]}${data["mqtt-port"] !== undefined ? `:${data["mqtt-port"]}` : ""}`
    : undefined;
  const details = [
    data.name,
    data.cameraid ? `camera: ${data.cameraid}` : undefined,
    data.metadatagenpolicy,
    broker,
    publishImage ? "image" : undefined,
  ].filter((item): item is string => Boolean(item));

  return (
    <PipelineNodeCard
      title={
        simpleGraph
          ? "SceneScape Publisher"
          : "sscape_post_inference_data_publish"
      }
      nodeType="sscape_post_inference_data_publish"
      roleClasses={PIPELINE_NODE_ROLE_CLASSES.metadataPublish}
      minWidthClass="min-w-[18.125rem]"
      details={
        details.length > 0 && (
          <div className="flex items-center gap-1 flex-wrap text-xs text-node-body-text">
            {details.map((item, index) => (
              <span key={item} className="flex items-center gap-1">
                {index > 0 && <span className="text-node-separator">•</span>}
                <span>{item}</span>
              </span>
            ))}
          </div>
        )
      }
      icon={
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0"
        />
      }
    />
  );
};

export default SscapePostInferenceDataPublishNode;
