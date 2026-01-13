import { FlaskConical } from "lucide-react";

type TestPipelineButtonProps = {
  onTest: () => void;
};

const TestPipelineButton = ({ onTest }: TestPipelineButtonProps) => (
  <button
    onClick={onTest}
    className="w-[160px] bg-classic-blue dark:text-[#242528] font-medium dark:bg-energy-blue dark:hover:bg-energy-blue-tint-1 hover:bg-classic-blue-hover disabled:bg-gray-400 text-white px-3 py-2 shadow-lg transition-colors flex items-center gap-2"
    title="Test Pipeline"
  >
    <FlaskConical className="w-5 h-5" />
    <span>Test pipeline</span>
  </button>
);

export default TestPipelineButton;
