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

export type GatedModelLink = {
  name: string;
  url: string | null;
};

type LicenseAcknowledgementDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  models: readonly GatedModelLink[];
  hubName: string;
  onConfirm: () => void;
};

export const LicenseAcknowledgementDialog = ({
  open,
  onOpenChange,
  models,
  hubName,
  onConfirm,
}: LicenseAcknowledgementDialogProps) => {
  const isMultiple = models.length > 1;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Additional action required</DialogTitle>
          <DialogDescription>
            {isMultiple
              ? `These models require additional action to acknowledge their licenses before they can be installed. Visit each model page on ${hubName}, accept the license terms, and then continue with the installation.`
              : `This model requires additional action to acknowledge its license before it can be installed. Visit the model page on ${hubName}, accept the license terms, and then continue with the installation.`}
          </DialogDescription>
        </DialogHeader>
        <ul className="space-y-2">
          {models.map((model) => (
            <li key={model.name} className="text-sm">
              {model.url ? (
                <a
                  href={model.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={model.url}
                  className="inline-flex items-center gap-1 break-all text-primary underline-offset-4 hover:underline"
                >
                  <ExternalLink className="h-4 w-4 shrink-0" />
                  {model.name}
                </a>
              ) : (
                <span className="font-medium">{model.name}</span>
              )}
            </li>
          ))}
        </ul>
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
};
