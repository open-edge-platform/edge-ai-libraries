import { Play } from "lucide-react";

type RunPipelineButtonProps = {
  onRun: () => void;
  isRunning?: boolean;
};

const RunPipelineButton = ({ onRun, isRunning }: RunPipelineButtonProps) => {
  return (
    <button
      onClick={onRun}
      disabled={isRunning}
      className="w-[160px] bg-classic-blue dark:text-[#242528] font-medium dark:bg-energy-blue dark:hover:bg-energy-blue-tint-1 hover:bg-classic-blue-hover disabled:bg-gray-400 text-white px-3 py-2 shadow-lg transition-colors flex items-center gap-2"
      title="Run Performance Test"
    >
      <Play className="w-5 h-5" />
      <span>Run pipeline</span>
    </button>
  );
};

export default RunPipelineButton;
