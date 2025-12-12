import { Play } from "lucide-react";

type RunPipelineButtonProps = {
  isRunning: boolean;
  onRun: () => void;
};

const RunPerformanceTestButton = ({
  isRunning,
  onRun,
}: RunPipelineButtonProps) => (
  <button
    onClick={onRun}
    disabled={isRunning}
    className="w-[160px] bg-primary hover:bg-green-700 disabled:bg-gray-400 text-white px-3 py-2 shadow-lg transition-colors flex items-center gap-2"
    title="Run Pipeline"
  >
    <Play className="w-5 h-5" />
    <span>Run pipeline</span>
  </button>
);

export default RunPerformanceTestButton;
