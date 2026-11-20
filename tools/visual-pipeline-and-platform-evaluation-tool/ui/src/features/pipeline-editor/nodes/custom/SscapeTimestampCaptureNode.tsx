// SPDX-License-Identifier: Apache-2.0
import { usePipelineEditorContext } from "../../PipelineEditorContext.ts";
import { PipelineNodeCard, PIPELINE_NODE_ROLE_CLASSES } from "../shared";

export const SscapeTimestampCaptureNodeWidth = 260;

type SscapeTimestampCaptureNodeProps = {
  data: {
    name?: string;
    "ntp-server"?: string;
    "use-frame-ntp-timestamp"?: boolean | string;
  };
};

const SscapeTimestampCaptureNode = ({
  data,
}: SscapeTimestampCaptureNodeProps) => {
  const { simpleGraph } = usePipelineEditorContext();
  const useFrameNtp = String(data["use-frame-ntp-timestamp"]) === "true";
  const details = [
    data.name,
    data["ntp-server"] ? `ntp: ${data["ntp-server"]}` : undefined,
    useFrameNtp ? "frame NTP" : undefined,
  ].filter((item): item is string => Boolean(item));

  return (
    <PipelineNodeCard
      title={simpleGraph ? "Timestamp Capture" : "sscape_timestamp_capture"}
      nodeType="sscape_timestamp_capture"
      roleClasses={PIPELINE_NODE_ROLE_CLASSES.metadata}
      minWidthClass="min-w-[16.25rem]"
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
          d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      }
    />
  );
};

export default SscapeTimestampCaptureNode;
