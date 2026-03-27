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
      className="w-[10rem] bg-primary hover:bg-primary-90 disabled:bg-muted text-primary-foreground px-3 py-2 shadow-lg transition-colors flex items-center gap-2 font-medium"
      title="Run Performance Test"
    >
      <Play className="w-5 h-5" />
      <span>Run pipeline</span>
    </button>
  );
};

export default RunPipelineButton;
