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
    className="w-[160px] bg-red-600 dark:bg-[#f88f8f] dark:text-[#242528] dark:hover:bg-red-400 font-medium hover:bg-red-700 disabled:bg-gray-400 text-white px-3 py-2 shadow-lg transition-colors flex items-center gap-2"
    title="Stop Pipeline"
  >
    <Square className="w-5 h-5" />
    <span>Stop pipeline</span>
  </button>
);

export default StopPipelineButton;
