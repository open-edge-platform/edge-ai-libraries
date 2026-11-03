import { Download, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type LicenseAcknowledgementDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  modelUrl: string | null;
  hubName: string;
  onConfirm: () => void;
};

export const LicenseAcknowledgementDialog = ({
  open,
  onOpenChange,
  modelUrl,
  hubName,
  onConfirm,
}: LicenseAcknowledgementDialogProps) => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>Additional action required</DialogTitle>
        <DialogDescription>
          This model requires additional action to acknowledge its license
          before it can be installed. Visit the model page on {hubName}, accept
          the license terms, and then continue with the installation.
        </DialogDescription>
      </DialogHeader>
      {modelUrl && (
        <a
          href={modelUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 break-all text-sm text-primary underline-offset-4 hover:underline"
        >
          <ExternalLink className="h-4 w-4 shrink-0" />
          {modelUrl}
        </a>
      )}
      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button onClick={onConfirm}>
          <Download className="mr-2 h-4 w-4" />
          Proceed with install
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
);
