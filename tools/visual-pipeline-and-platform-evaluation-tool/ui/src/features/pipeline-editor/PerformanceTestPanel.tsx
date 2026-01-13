import { Play, Square } from "lucide-react";
import FpsDisplay from "./FpsDisplay";

type PerformanceTestPanelProps = {
  isRunning: boolean;
  isStopping: boolean;
  onRun: () => void;
  onStop: () => void;
  completedVideoPath: string | null;
};

const PerformanceTestPanel = ({
  isRunning,
  isStopping,
  onRun,
  onStop,
  completedVideoPath,
}: PerformanceTestPanelProps) => {
  return (
    <div className="w-full h-full bg-background p-4 space-y-4">
      <h2 className="text-lg font-semibold">Test pipeline</h2>

      <div className="space-y-4">
        <div>
          <div className="flex gap-2">
            {isRunning ? (
              <button
                onClick={onStop}
                disabled={isStopping}
                className="flex-1 bg-red-600 dark:bg-red-700 hover:bg-red-700 dark:hover:bg-red-800 disabled:bg-gray-400 text-white px-4 py-2 transition-colors flex items-center justify-center gap-2"
                title="Stop Performance Test"
              >
                <Square className="w-5 h-5" />
                <span>{isStopping ? "Stopping..." : "Stop test"}</span>
              </button>
            ) : (
              <button
                onClick={onRun}
                className="flex-1 bg-classic-blue dark:bg-energy-blue hover:bg-classic-blue-hover dark:hover:bg-energy-blue-tint-1 text-white dark:text-[#242528] px-4 py-2 transition-colors flex items-center justify-center gap-2"
                title="Run Performance Test"
              >
                <Play className="w-5 h-5" />
                <span>Run test</span>
              </button>
            )}
          </div>
        </div>

        {isRunning && (
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-2">
              FPS Monitor
            </h3>
            <FpsDisplay />
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
      </div>
    </div>
  );
};

export default PerformanceTestPanel;
