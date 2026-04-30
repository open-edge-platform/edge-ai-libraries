import { Play } from "lucide-react";
import { PipelineToolbarButton } from "./shared";

type RunPipelineButtonProps = {
  onRun: () => void;
  isRunning?: boolean;
};

const RunPipelineButton = ({ onRun, isRunning }: RunPipelineButtonProps) => (
  <PipelineToolbarButton
    onClick={onRun}
    disabled={isRunning}
    title="Run Performance Test"
    icon={<Play className="w-5 h-5" />}
    label={<span>Run pipeline</span>}
    variant="primary"
    widthClassName="w-[10rem]"
  />
);

export default RunPipelineButton;
