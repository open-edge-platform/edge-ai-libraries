import { useEffect, useRef } from "react";
import { MetricsDashboard } from "@/features/metrics/MetricsDashboard.tsx";
import WebRTCVideoPlayer from "@/features/webrtc/WebRTCVideoPlayer.tsx";
import { useFrozenMetrics } from "@/hooks/useFrozenMetrics";

type PerformanceTestPanelProps = {
  isRunning: boolean;
  completedVideoPath: string | null;
  pipelineId?: string;
  livePreviewEnabled?: boolean;
  liveStreamUrl?: string | null;
};

const PerformanceTestPanel = ({
  isRunning,
  completedVideoPath,
  pipelineId,
  livePreviewEnabled = false,
  liveStreamUrl,
}: PerformanceTestPanelProps) => {
  const { frozenHistory, frozenSummary, startRecording, freezeSnapshot } =
    useFrozenMetrics();
  const prevIsRunningRef = useRef(false);

  useEffect(() => {
    const wasRunning = prevIsRunningRef.current;
    prevIsRunningRef.current = isRunning;

    if (!wasRunning && isRunning) {
      startRecording();
    } else if (wasRunning && !isRunning) {
      freezeSnapshot(null);
    }
  }, [isRunning, startRecording, freezeSnapshot]);

  return (
    <div className="w-full h-full bg-background p-4 space-y-4">
      <h2 className="text-lg font-semibold">Test pipeline</h2>

      <div className="space-y-4">
        {livePreviewEnabled && (isRunning || !!liveStreamUrl) && (
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-2">
              Live Preview
            </h3>
            {liveStreamUrl ? (
              <WebRTCVideoPlayer
                pipelineId={pipelineId}
                streamUrl={liveStreamUrl}
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                Waiting for live stream to be published...
              </p>
            )}
          </div>
        )}

        {completedVideoPath && (
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-2">
              Output Video
            </h3>
            <video
              controls
              className="w-full h-auto border border-gray-300 rounded"
              src={`/assets${completedVideoPath}`}
            >
              Your browser does not support the video tag.
            </video>
          </div>
        )}

        {isRunning && <MetricsDashboard />}
        {!isRunning && frozenSummary && (
          <MetricsDashboard
            historyOverride={frozenHistory}
            metricsOverride={frozenSummary}
          />
        )}
      </div>
    </div>
  );
};

export default PerformanceTestPanel;
