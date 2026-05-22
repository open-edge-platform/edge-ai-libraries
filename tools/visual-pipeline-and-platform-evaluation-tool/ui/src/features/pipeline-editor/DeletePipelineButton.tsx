import { Trash2 } from "lucide-react";
import { useDeletePipelineMutation } from "@/api/api.generated";
import { toast } from "@/lib/toast";
import { useNavigate } from "react-router";
import { handleApiError } from "@/lib/apiUtils";
import { PipelineToolbarButton } from "./shared";

interface DeletePipelineButtonProps {
  pipelineId: string;
  pipelineName: string;
}

const DeletePipelineButton = ({
  pipelineId,
  pipelineName,
}: DeletePipelineButtonProps) => {
  const [deletePipeline, { isLoading }] = useDeletePipelineMutation();
  const navigate = useNavigate();

  const handleDelete = async () => {
    const confirmed = window.confirm(
      `Are you sure you want to delete pipeline "${pipelineName}"?`,
    );

    if (!confirmed) return;

    try {
      await deletePipeline({ pipelineId }).unwrap();
      toast.success(`Pipeline "${pipelineName}" deleted successfully`);
      navigate("/");
    } catch (error) {
      handleApiError(error, "Failed to delete pipeline");
    }
  };

  return (
    <PipelineToolbarButton
      onClick={handleDelete}
      disabled={isLoading}
      icon={<Trash2 className="w-5 h-5" />}
      label={<span>{isLoading ? "Deleting..." : "Delete"}</span>}
      variant="destructive"
      className="p-2"
    />
  );
};

export default DeletePipelineButton;
