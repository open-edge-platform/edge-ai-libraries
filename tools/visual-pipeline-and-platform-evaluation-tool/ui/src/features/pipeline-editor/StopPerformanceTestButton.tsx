import { Square } from "lucide-react";

type StopPipelineButtonProps = {
  isStopping: boolean;
  onStop: () => void;
};

const StopPerformanceTestButton = ({
  isStopping,
  onStop,
}: StopPipelineButtonProps) => (
  <button
    onClick={onStop}
    disabled={isStopping}
    className="w-[160px] bg-red-600 hover:bg-red-700 disabled:bg-gray-400 text-white px-3 py-2 shadow-lg transition-colors flex items-center gap-2"
    title="Stop Pipeline"
  >
    <Square className="w-5 h-5" />
    <span>Stop pipeline</span>
  </button>
);

export default StopPerformanceTestButton;
