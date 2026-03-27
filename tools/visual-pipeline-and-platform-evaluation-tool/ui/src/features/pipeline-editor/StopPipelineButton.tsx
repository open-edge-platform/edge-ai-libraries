import { Square } from "lucide-react";

type StopPipelineButtonProps = {
  isStopping: boolean;
  onStop: () => void;
};

const StopPipelineButton = ({
  isStopping,
  onStop,
}: StopPipelineButtonProps) => (
  <button
    onClick={onStop}
    disabled={isStopping}
    className="w-[10rem] bg-destructive hover:bg-destructive-90 disabled:bg-muted text-primary-foreground px-3 py-2 shadow-lg transition-colors flex items-center gap-2 font-medium"
    title="Stop Pipeline"
  >
    <Square className="w-5 h-5" />
    <span>Stop pipeline</span>
  </button>
);

export default StopPipelineButton;
