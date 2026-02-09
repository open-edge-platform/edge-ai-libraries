import { TestProgressIndicator } from "@/features/pipeline-tests/TestProgressIndicator.tsx";

type PerformanceTestPanelProps = {
  isRunning: boolean;
  completedVideoPath: string | null;
};

const PerformanceTestPanel = ({
  isRunning,
  completedVideoPath,
}: PerformanceTestPanelProps) => {
  return (
    <div className="w-full h-full bg-background p-4 space-y-4">
      <h2 className="text-lg font-semibold">Test pipeline</h2>

      <div className="space-y-4">
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

        {(isRunning || completedVideoPath) && <TestProgressIndicator />}
      </div>
    </div>
  );
};

export default PerformanceTestPanel;
