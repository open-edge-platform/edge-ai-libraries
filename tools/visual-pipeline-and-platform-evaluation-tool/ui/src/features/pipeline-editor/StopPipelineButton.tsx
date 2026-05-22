import { Square } from "lucide-react";
import { PipelineToolbarButton } from "./shared";

type StopPipelineButtonProps = {
  isStopping: boolean;
  onStop: () => void;
};

const StopPipelineButton = ({
  isStopping,
  onStop,
}: StopPipelineButtonProps) => (
  <PipelineToolbarButton
    onClick={onStop}
    disabled={isStopping}
    title="Stop Pipeline"
    icon={<Square className="w-5 h-5" />}
    label={<span>Stop pipeline</span>}
    variant="destructive"
    widthClassName="w-[10rem]"
  />
);

export default StopPipelineButton;
