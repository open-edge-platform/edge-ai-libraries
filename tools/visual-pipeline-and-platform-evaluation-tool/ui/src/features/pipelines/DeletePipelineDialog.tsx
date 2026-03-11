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
import { type Pipeline, useDeletePipelineMutation } from "@/api/api.generated";
import { toast } from "sonner";
import { isApiError } from "@/lib/apiUtils";
import { Trash2 } from "lucide-react";

type DeletePipelineDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pipeline: Pipeline | null;
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
        : "Unknown error";
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
            <p>
              Are you sure you want to delete <b>{pipeline?.name}</b> pipeline?
            </p>
            {pipeline && pipeline.variants.length > 0 && (
              <p>
                This will also delete{" "}
                <b>
                  {pipeline.variants.length !== 1
                    ? "all"
                    : pipeline.variants[0].name}
                </b>{" "}
                variant
                {pipeline.variants.length !== 1 ? "s" : ""}.
              </p>
            )}
            <p>This action cannot be undone!</p>
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
