import { Trash2 } from "lucide-react";
import { useDeletePipelineMutation } from "@/api/api.generated";
import { toast } from "sonner";
import { useNavigate } from "react-router";
import { handleApiError } from "@/lib/apiUtils";

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
    <button
      onClick={handleDelete}
      disabled={isLoading}
      className="bg-destructive hover:bg-destructive-90 text-primary-foreground font-medium disabled:bg-destructive-40 p-2 flex items-center gap-2 transition-colors"
    >
      <Trash2 className="w-5 h-5" />
      <span>{isLoading ? "Deleting..." : "Delete"}</span>
    </button>
  );
};

export default DeletePipelineButton;
