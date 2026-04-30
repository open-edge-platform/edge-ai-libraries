import { useNavigate } from "react-router";
import { ChevronDown } from "lucide-react";
import { useState } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { type Variant } from "@/api/api.generated";
import { UnsavedChangesDialog } from "@/components/shared/UnsavedChangesDialog";

interface PipelineVariantSelectProps {
  pipelineId: string;
  currentVariant: string;
  variants: Variant[];
  source?: string | null;
  hasUnsavedChanges?: boolean;
  disabled?: boolean;
}

export const PipelineVariantSelect = ({
  pipelineId,
  currentVariant,
  variants,
  source,
  hasUnsavedChanges = false,
}: PipelineVariantSelectProps) => {
  const navigate = useNavigate();
  const [showDialog, setShowDialog] = useState(false);
  const [pendingVariantId, setPendingVariantId] = useState<string | null>(null);

  const currentVariantObj = variants.find((v) => v.id === currentVariant);
  const currentVariantName = currentVariantObj?.name ?? currentVariant;

  const handleVariantChange = (variantId: string) => {
    if (hasUnsavedChanges) {
      setPendingVariantId(variantId);
      setShowDialog(true);
    } else {
      navigateToVariant(variantId);
    }
  };

  const navigateToVariant = (variantId: string) => {
    const searchParams = source ? `?source=${source}` : "";
    navigate(`/pipelines/${pipelineId}/${variantId}${searchParams}`);
  };

  const handleDiscard = () => {
    if (pendingVariantId) {
      navigateToVariant(pendingVariantId);
      setPendingVariantId(null);
    }
    setShowDialog(false);
  };

  return (
    <>
      <div className="flex items-center gap-1">
        <span>({currentVariantName})</span>
        <DropdownMenu>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuTrigger className="size-8 flex items-center justify-center hover:bg-accent dark:hover:bg-accent/50 transition-colors">
                <ChevronDown className="size-4 text-muted-foreground" />
              </DropdownMenuTrigger>
            </TooltipTrigger>
            <TooltipContent side="bottom">Switch variant</TooltipContent>
          </Tooltip>
          <DropdownMenuContent align="start">
            <p className="px-2 py-1 text-xs uppercase tracking-wide text-muted-foreground">
              VARIANTS
            </p>
            {variants.map((variant) => (
              <DropdownMenuItem
                key={variant.id}
                onClick={() => handleVariantChange(variant.id)}
              >
                {variant.name}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <UnsavedChangesDialog
        open={showDialog}
        onOpenChange={setShowDialog}
        onDiscard={handleDiscard}
      />
    </>
  );
};
