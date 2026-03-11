import { useNavigate } from "react-router";
import { ChevronDown } from "lucide-react";
import { useState } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { type Variant } from "@/api/api.generated";
import { UnsavedChangesDialog } from "@/components/shared/UnsavedChangesDialog";

interface PipelineVariantSelectProps {
  pipelineId: string;
  currentVariant: string;
  variants: Variant[];
  source?: string | null;
  hasUnsavedChanges?: boolean;
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
          <DropdownMenuTrigger className="p-1 hover:bg-accent rounded transition-colors">
            <ChevronDown className="size-4 text-muted-foreground" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
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
