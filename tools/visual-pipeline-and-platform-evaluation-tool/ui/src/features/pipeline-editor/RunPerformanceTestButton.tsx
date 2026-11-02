import { Play } from "lucide-react";
import { PipelineToolbarButton } from "./shared";

type RunPipelineButtonProps = {
  onRun: () => void;
  isRunning?: boolean;
  disabled?: boolean;
};

const RunPipelineButton = ({
  onRun,
  isRunning,
  disabled,
}: RunPipelineButtonProps) => (
  <PipelineToolbarButton
    onClick={onRun}
    disabled={isRunning || disabled}
    title="Run Performance Test"
    icon={<Play className="w-5 h-5" />}
    label={<span>Run pipeline</span>}
    variant="default"
    widthClassName="w-[10rem]"
  />
);

export default RunPipelineButton;
