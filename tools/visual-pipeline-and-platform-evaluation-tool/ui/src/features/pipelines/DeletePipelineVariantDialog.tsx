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
import { useDeleteVariantMutation } from "@/api/api.generated";
import { toast } from "sonner";
import { handleApiError } from "@/lib/apiUtils";
import { Trash2 } from "lucide-react";

type DeletePipelineVariantDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pipelineId: string;
  variantId: string;
  variantName: string;
  onSuccess?: () => void;
};

export const DeletePipelineVariantDialog = ({
  open,
  onOpenChange,
  pipelineId,
  variantId,
  variantName,
  onSuccess,
}: DeletePipelineVariantDialogProps) => {
  const [deleteVariant, { isLoading: isDeleting }] = useDeleteVariantMutation();

  const handleDeleteConfirm = async () => {
    try {
      await deleteVariant({ pipelineId, variantId }).unwrap();
      toast.success(`Variant "${variantName}" deleted successfully`);
      onOpenChange(false);
      onSuccess?.();
    } catch (error) {
      handleApiError(error, "Failed to delete variant");
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="top-[20%] translate-y-0">
        <AlertDialogHeader>
          <AlertDialogMedia>
            <Trash2 className="text-destructive" />
          </AlertDialogMedia>
          <AlertDialogTitle>Delete Variant?</AlertDialogTitle>
          <AlertDialogDescription className="text-justify">
            <p>
              Are you sure you want to delete variant <b>{variantName}</b>?
            </p>
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
