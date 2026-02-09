import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useDeletePipelineMutation } from "@/api/api.generated";
import { toast } from "sonner";
import { isApiError } from "@/lib/apiUtils";
import { Trash2 } from "lucide-react";

type DeletePipelineDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pipeline: {
    id: string;
    name: string;
    variantCount: number;
  } | null;
  onSuccess?: () => void;
};

export const DeletePipelineDialog = ({
  open,
  onOpenChange,
  pipeline,
  onSuccess,
}: DeletePipelineDialogProps) => {
  const [deletePipeline, { isLoading: isDeleting }] =
    useDeletePipelineMutation();

  const handleDeleteConfirm = async () => {
    if (!pipeline) return;

    try {
      await deletePipeline({ pipelineId: pipeline.id }).unwrap();
      toast.success(`Pipeline "${pipeline.name}" deleted successfully`);
      onOpenChange(false);
      onSuccess?.();
    } catch (error) {
      const errorMessage = isApiError(error)
        ? error.data.message
        : "Failed to delete pipeline";
      toast.error(`Failed to delete pipeline: ${errorMessage}`);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="top-[20%] translate-y-0">
        <AlertDialogHeader>
          <AlertDialogMedia>
            <Trash2 className="text-destructive" />
          </AlertDialogMedia>
          <AlertDialogTitle>Delete Pipeline?</AlertDialogTitle>
          <AlertDialogDescription className="text-justify">
            Are you sure you want to delete <b>{pipeline?.name}</b> pipeline?
            {pipeline && pipeline.variantCount > 0 && (
              <>
                {" "}
                This will also delete all {pipeline.variantCount} variant
                {pipeline.variantCount !== 1 ? "s" : ""}.
              </>
            )}{" "}
            This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            onClick={handleDeleteConfirm}
            disabled={isDeleting}
          >
            {isDeleting ? "Deleting..." : "Delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};
