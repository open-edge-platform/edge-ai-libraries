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

      <div className="space-y-4 pb-8">
        {livePreviewEnabled && (isRunning || !!liveStreamUrl) && (
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-2">
              Live Preview
            </h3>
            {liveStreamUrl ? (
              <div className="mx-auto w-full max-w-[36rem] overflow-hidden rounded border border-input bg-black">
                <div className="aspect-video">
                  <WebRTCVideoPlayer
                    pipelineId={pipelineId}
                    streamUrl={liveStreamUrl}
                  />
                </div>
              </div>
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
            <div className="mx-auto w-full max-w-[36rem] overflow-hidden rounded border border-input bg-black">
              <div className="aspect-video">
                <video
                  controls
                  className="block h-full w-full object-contain"
                  src={`/assets${completedVideoPath}`}
                >
                  Your browser does not support the video tag.
                </video>
              </div>
            </div>
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
