import { Play, Square } from "lucide-react";

type RunPipelineButtonProps = {
  isRunning: boolean;
  isStopping: boolean;
  onRun: () => void;
  onStop: () => void;
};

const RunPipelineButton = ({
  isRunning,
  isStopping,
  onRun,
  onStop,
}: RunPipelineButtonProps) => {
  if (isRunning) {
    return (
      <button
        onClick={onStop}
        disabled={isStopping}
        className="w-[160px] bg-red-600 dark:bg-red-700 hover:bg-red-700 dark:hover:bg-red-800 disabled:bg-gray-400 text-white px-3 py-2 shadow-lg transition-colors flex items-center justify-center gap-2"
        title="Stop Performance Test"
      >
        <Square className="w-5 h-5" />
        <span>{isStopping ? "Stopping..." : "Stop test"}</span>
      </button>
    );
  }

  return (
    <button
      onClick={onRun}
      className="w-[160px] bg-classic-blue dark:text-[#242528] font-medium dark:bg-energy-blue dark:hover:bg-energy-blue-tint-1 hover:bg-classic-blue-hover disabled:bg-gray-400 text-white px-3 py-2 shadow-lg transition-colors flex items-center gap-2"
      title="Run Performance Test"
    >
      <Play className="w-5 h-5" />
      <span>Run pipeline</span>
    </button>
  );
};

export default RunPipelineButton;
